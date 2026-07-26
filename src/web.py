"""Cloud Run HTTP API и Telegram webhook."""

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from decimal import Decimal, InvalidOperation
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from httpx import TimeoutException, TransportError
from pydantic import BaseModel, Field
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut

from src.admin_cloud import cloud_runtime_status
from src.auth import Principal, verify_firebase_bearer, verify_telegram_init_data
from src.billing import telegram_subscription_metrics, telegram_subscription_status
from src.bot import (
    format_card,
    format_public_teaser,
    format_sources,
    is_publishable,
    localized,
    select_publishable_decisions,
    telegram_language,
)
from src.chat import (
    ChatIntent,
    classify_chat_intent,
    effective_chat_id,
    help_text,
    incoming_text,
    search_prompt_text,
    welcome_text,
)
from src.cloud_jobs import CloudJobLauncher
from src.config import Settings
from src.content import audience_poll, deal_analysis, market_pulse, price_drop, weekly_review
from src.domain.ids import (
    delivery_id,
    operation_id,
    publication_event_id,
    verification_key,
)
from src.domain.models import (
    OutboxRecord,
    OutboxState,
    Outcome,
    ProcessingState,
    PublicationEvent,
    UserAction,
    UserSettings,
)
from src.news import DubaiAutoNewsClient, format_news
from src.search import build_saved_search, parse_search
from src.service import DealService, EvaluatedListing
from src.storage import snapshot_hash
from src.tasks import CloudTaskDispatcher
from src.verification import EXTRACTOR_VERSION, evidence_is_active
from src.whatsapp import WhatsAppAdapter, WhatsAppConfig

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
settings = Settings.from_env()
service = DealService.from_settings(settings)
news_client = DubaiAutoNewsClient(
    settings.auto_news_rss_url,
    settings.request_timeout_seconds,
    settings.auto_news_max_age_days,
    settings.auto_news_limit,
)
app = FastAPI(title="Dubai Deal Sniper", version="1.1.0")


class TelegramReplyClient:
    """Отправляет ответ в ту же тему личных сообщений канала, если она задана."""

    def __init__(self, bot: Bot, message: dict[str, Any]) -> None:
        self._bot = bot
        topic = message.get("direct_messages_topic")
        topic_id = topic.get("topic_id") if isinstance(topic, dict) else None
        if not isinstance(topic_id, int):
            topic_id = message.get("message_thread_id")
        self._topic_id = topic_id if isinstance(topic_id, int) else None

    async def send_message(self, **kwargs: Any) -> Any:
        """Дополняет sendMessage идентификатором direct-messages topic."""
        if self._topic_id is not None:
            kwargs["direct_messages_topic_id"] = self._topic_id
        return await self._bot.send_message(**kwargs)
_market_cache: list[tuple[Any, Any]] = []
_market_cache_at = 0.0
_market_cache_lock = asyncio.Lock()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://avo-deal-sniper.web.app",
        "https://avo-deal-sniper.firebaseapp.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def main_chat_keyboard() -> ReplyKeyboardMarkup:
    """Показывает основные действия без знания технических команд."""
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton("🚗 Find a car"), KeyboardButton("📰 Dubai auto news")],
        [KeyboardButton("📊 Market overview"), KeyboardButton("ℹ️ How it works")],
        [KeyboardButton("⭐ Upgrade to Pro")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


@app.middleware("http")
async def restore_gateway_authorization(request: Any, call_next: Any) -> Any:
    """Восстанавливает Firebase bearer, сохранённый API Gateway при backend OIDC."""
    forwarded = request.headers.get("x-forwarded-authorization")
    headers = [
        (name, value)
        for name, value in request.scope.get("headers", [])
        if name.lower() != b"authorization"
    ]
    if forwarded:
        headers.append((b"authorization", forwarded.encode("latin-1")))
    request.scope["headers"] = headers
    return await call_next(request)


class ProcessingTask(BaseModel):
    listing_id: str
    content_hash: str
    engine_version: str


class DeliveryTask(BaseModel):
    delivery_id: str
    decision_id: str
    target_id: str
    listing_id: str
    content_hash: str
    text: str
    engine_version: str | None = None
    template_version: str = "pro/v1"
    format: str = "telegram"
    image_url: str | None = None


class SourceAdminRequest(BaseModel):
    enabled: bool


class OutboxReconciliationRequest(BaseModel):
    action: str


class TmaAuthRequest(BaseModel):
    init_data: str


class OutcomeRequest(BaseModel):
    listing_id: str
    decision_content_hash: str
    status: str
    purchase_price_aed: Decimal | None = None
    actual_cost_aed: Decimal | None = None
    sale_price_aed: Decimal | None = None
    hold_days: int | None = None


class FavoriteRequest(BaseModel):
    listing_id: str
    favorite: bool = True


class TmaSettingsRequest(BaseModel):
    """Редактируемые пользователем фильтры без возможности сменить владельца."""

    max_budget_aed: Decimal | None = Field(default=None, gt=0)
    min_profit_aed: Decimal = Field(default=Decimal("5000"), ge=0)
    min_roi_percent: Decimal = Field(default=Decimal("10"), ge=0)
    makes: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    min_year: int | None = Field(default=None, ge=1950, le=2100)
    max_year: int | None = Field(default=None, ge=1950, le=2100)
    max_mileage_km: int | None = Field(default=None, ge=0)
    specifications: list[str] = Field(default_factory=list)
    body_types: list[str] = Field(default_factory=list)


class TmaSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class TmaSearchStateRequest(BaseModel):
    enabled: bool


class ContentDeliveryTask(BaseModel):
    delivery_id: str
    publication_event_id: str
    target_id: str
    text: str
    template_version: str = "content/v1"
    image_url: str | None = None


class WhatsAppDeliveryTask(BaseModel):
    delivery_id: str
    publication_event_id: str
    recipient: str
    template_name: str
    language_code: str = "en_US"
    components: list[dict[str, Any]] = Field(default_factory=list)
    opted_in: bool


async def telegram_update_lease(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> AsyncIterator[bool]:
    """Фиксирует processing/completed/failed и допускает повтор после истечения lease."""
    expected = settings.telegram_webhook_secret
    update_id = update.get("update_id")
    if (
        not settings.delivery_enabled
        or (expected and x_telegram_bot_api_secret_token != expected)
        or not isinstance(update_id, int)
    ):
        yield True
        return
    claimed = await asyncio.to_thread(
        service.repository.claim_telegram_update,
        update_id,
        os.getenv("K_REVISION", "local-webhook"),
    )
    if not claimed:
        yield False
        return
    try:
        yield True
    except Exception as error:
        await asyncio.to_thread(
            service.repository.finish_telegram_update,
            update_id,
            ProcessingState.FAILED,
            f"{type(error).__name__}: {error}",
        )
        raise
    else:
        await asyncio.to_thread(
            service.repository.finish_telegram_update,
            update_id,
            ProcessingState.COMPLETED,
        )


def firebase_principal(authorization: str | None, *, require_admin: bool) -> Principal:
    try:
        principal = verify_firebase_bearer(
            authorization,
            settings.google_cloud_project,
            settings.admin_emails,
        )
    except PermissionError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    if require_admin and not principal.admin:
        raise HTTPException(status_code=403, detail="Требуется роль администратора")
    return principal


async def current_market_snapshot() -> list[tuple[Any, Any]]:
    """Объединяет параллельные TMA-запросы в одно чтение Firestore на 30 секунд."""
    global _market_cache, _market_cache_at
    if _market_cache and time.monotonic() - _market_cache_at < 30:
        return _market_cache
    async with _market_cache_lock:
        if _market_cache and time.monotonic() - _market_cache_at < 30:
            return _market_cache
        _market_cache = await asyncio.to_thread(service.repository.current_decisions, 10_000)
        _market_cache_at = time.monotonic()
        return _market_cache


def require_internal_task(secret: str | None, task_name: str | None) -> None:
    """Принимает запрос только от Cloud Tasks и проверяет дополнительный секрет."""
    if not task_name:
        raise HTTPException(status_code=403, detail="Запрос пришёл не из Cloud Tasks")
    expected = settings.internal_task_secret
    if expected and secret != expected:
        raise HTTPException(status_code=403, detail="Неверный внутренний секрет")


async def launch_scan(source_name: str | None = None) -> list[str]:
    statuses = service.source_statuses()
    names = (
        [source_name] if source_name else [name for name, enabled in statuses.items() if enabled]
    )
    names = [name for name in names if name in statuses and statuses[name]]
    if not names:
        raise ValueError("Нет включённых источников")
    launcher = CloudJobLauncher(settings)
    await launcher.run_collectors(names)
    return names


def default_user_settings(user_id: int, language_code: str = "en") -> UserSettings:
    return UserSettings(
        user_id=user_id,
        min_profit_aed=settings.target_profit_aed,
        min_roi_percent=settings.min_roi_percent,
        language_code=telegram_language(language_code),
    )


def pro_subscription_text(active: bool) -> str:
    """Формирует прозрачное предложение единственного платного тарифа."""
    status = "Your Pro access is active." if active else "Your current plan is Free."
    return (
        f"<b>Dubai Deal Sniper Pro — {settings.pro_price_aed} AED / 30 days</b>\n\n"
        f"{status}\n\n"
        "Pro includes full verified deal cards: listing photo and link, market range, "
        "maximum purchase price, costs, expected profit, ROI and risks.\n\n"
        f"Telegram payment: {settings.pro_price_stars:,} Stars every 30 days."
    )


def pro_subscription_keyboard() -> InlineKeyboardMarkup | None:
    """Возвращает нативную Telegram Stars ссылку без раскрытия в исходном коде."""
    if not settings.telegram_pro_subscription_url:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Subscribe to Pro",
                    url=settings.telegram_pro_subscription_url,
                )
            ]
        ]
    )


def format_user_settings(value: UserSettings, language: str | None = None) -> str:
    language = telegram_language(language or value.language_code)
    budget = (
        f"{value.max_budget_aed:,.0f} AED"
        if value.max_budget_aed
        else localized(language, "без лимита", "no limit")
    )
    makes = ", ".join(value.makes) if value.makes else localized(language, "все марки", "all makes")
    return (
        localized(language, "Ваши настройки:\n", "Your settings:\n")
        + localized(language, f"Бюджет: {budget}\n", f"Budget: {budget}\n")
        + localized(
            language,
            f"Минимальная прибыль: {value.min_profit_aed:,.0f} AED\n",
            f"Minimum profit: {value.min_profit_aed:,.0f} AED\n",
        )
        + localized(
            language,
            f"Минимальный ROI: {value.min_roi_percent}%\n",
            f"Minimum ROI: {value.min_roi_percent}%\n",
        )
        + localized(language, f"Марки: {makes}\n\n", f"Makes: {makes}\n\n")
        + "/set_budget 150000\n/set_profit 7000\n/set_roi 12\n"
        "/set_makes Toyota,Lexus"
    )


def user_accepts(value: UserSettings, item: EvaluatedListing) -> bool:
    decision = item.decision
    if value.max_budget_aed and item.listing.price_aed > value.max_budget_aed:
        return False
    if decision.expected_profit_aed is None or decision.expected_profit_aed < value.min_profit_aed:
        return False
    if decision.roi_percent is None or decision.roi_percent < value.min_roi_percent:
        return False
    allowed_makes = {make.casefold() for make in value.makes}
    if allowed_makes and (item.listing.make or "").casefold() not in allowed_makes:
        return False
    allowed_models = {model.casefold() for model in value.models}
    if allowed_models and (item.listing.model or "").casefold() not in allowed_models:
        return False
    if value.min_year is not None and (item.listing.year or 0) < value.min_year:
        return False
    if value.max_year is not None and (item.listing.year or 9999) > value.max_year:
        return False
    if value.max_mileage_km is not None and (
        item.listing.mileage_km is None or item.listing.mileage_km > value.max_mileage_km
    ):
        return False
    specifications = {item.casefold() for item in value.specifications}
    return not specifications or (item.listing.specification or "").casefold() in specifications


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка процесса для Cloud Run."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Проверка обязательной production-конфигурации."""
    if settings.storage_backend == "firestore" and not settings.google_cloud_project:
        raise HTTPException(status_code=503, detail="Обязательная конфигурация отсутствует")
    if settings.delivery_enabled and not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="Delivery включена без Telegram token")
    actual_schema = await asyncio.to_thread(service.repository.schema_version)
    if actual_schema != settings.schema_version:
        raise HTTPException(
            status_code=503,
            detail=f"Несовместимая схема: runtime={settings.schema_version}, data={actual_schema}",
        )
    return {"status": "ready", "schema_version": actual_schema}


@app.get("/version")
async def version() -> dict[str, str]:
    """Версия API и детерминированного движка для smoke checks."""
    return {
        "git_commit": settings.git_commit,
        "runtime_image_digest": settings.runtime_image_digest,
        "api_version": "1.1.0",
        "engine_version": service.decision_engine.version,
        "schema_version": settings.schema_version,
        "financial_config_version": settings.financial_config_version,
    }


@app.get("/admin/overview")
async def admin_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Безопасный агрегат панели без секретных значений."""
    firebase_principal(authorization, require_admin=True)
    cloud = await asyncio.to_thread(
        cloud_runtime_status, settings.google_cloud_project, settings.google_cloud_region
    )
    subscription_metrics = await telegram_subscription_metrics(settings)
    return {
        "snapshot_count": await asyncio.to_thread(service.repository.count_snapshots),
        "sources": await asyncio.to_thread(service.repository.source_health),
        "source_switches": service.source_statuses(),
        "delivery_enabled": settings.delivery_enabled,
        "whatsapp_status": "ready"
        if settings.whatsapp_enabled
        and settings.whatsapp_access_token
        and settings.whatsapp_phone_number_id
        else "disabled",
        "schema_version": settings.schema_version,
        "operations": await asyncio.to_thread(service.repository.admin_summary),
        "cloud": cloud,
        "financial_config": {
            "version": settings.financial_config_version,
            "target_profit_aed": str(settings.target_profit_aed),
            "min_roi_percent": str(settings.min_roi_percent),
            "min_comparables": settings.min_comparables_count,
        },
        "subscription": {
            "price_aed": settings.pro_price_aed,
            "price_stars": settings.pro_price_stars,
            **subscription_metrics,
        },
        "referrals": await asyncio.to_thread(service.repository.referral_summary),
    }


@app.post("/admin/sources/{source_name}")
async def admin_source(
    source_name: str,
    request: SourceAdminRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str | bool]:
    principal = firebase_principal(authorization, require_admin=True)
    stable_operation_id = operation_id(
        "source-toggle",
        {"source": source_name, "enabled": request.enabled, "actor": principal.subject},
    )
    try:
        await asyncio.to_thread(service.set_source_enabled, source_name, request.enabled)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    await asyncio.to_thread(
        service.repository.record_audit_event,
        "admin_source_toggle",
        {
            "operation_id": stable_operation_id,
            "source": source_name,
            "enabled": request.enabled,
            "actor": principal.subject,
        },
    )
    return {"ok": True, "operation_id": stable_operation_id}


@app.post("/admin/outbox/{delivery_id}/reconcile")
async def admin_reconcile_outbox(
    delivery_id: str,
    request: OutboxReconciliationRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str | bool]:
    """Явно разрешает mark_sent, mark_failed или единственный retry_once."""
    principal = firebase_principal(authorization, require_admin=True)
    if request.action not in {"mark_sent", "mark_failed", "retry_once"}:
        raise HTTPException(status_code=422, detail="Недопустимое действие reconciliation")
    stable_operation_id = operation_id(
        "outbox-reconciliation",
        {
            "delivery_id": delivery_id,
            "action": request.action,
            "actor": principal.subject,
        },
    )
    existing = await asyncio.to_thread(service.repository.get_outbox, delivery_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Outbox запись не найдена")
    if request.action == "retry_once" and not existing.payload:
        raise HTTPException(
            status_code=409,
            detail="Legacy outbox не содержит воспроизводимый payload",
        )
    try:
        record = await asyncio.to_thread(
            service.repository.reconcile_outbox,
            delivery_id,
            request.action,
            stable_operation_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="Outbox запись не найдена")
    if request.action == "retry_once":
        payload = dict(record.payload)
        payload["_task_identity"] = stable_operation_id
        dispatcher = CloudTaskDispatcher(settings)
        if record.format == "telegram-content":
            await dispatcher.enqueue_content_delivery(payload)
        else:
            await dispatcher.enqueue_delivery(payload)
    return {
        "ok": True,
        "operation_id": stable_operation_id,
        "state": record.state.value,
    }


@app.get("/admin/outbox")
async def admin_outbox(
    state: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    firebase_principal(authorization, require_admin=True)
    try:
        parsed_state = OutboxState(state) if state else None
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Неизвестное состояние outbox") from error
    records = await asyncio.to_thread(service.repository.list_outbox, parsed_state, 100)
    return {
        "items": [
            {
                "delivery_id": item.delivery_id,
                "state": item.state.value,
                "template_version": item.template_version,
                "format": item.format,
                "last_attempt_at": item.last_attempt_at,
                "last_error": item.last_error,
                "retry_once_used": item.retry_once_used,
            }
            for item in records
        ]
    }


@app.get("/admin/preview")
async def admin_preview(
    authorization: str | None = Header(default=None),
) -> dict[str, str | None]:
    firebase_principal(authorization, require_admin=True)
    decisions = await asyncio.to_thread(service.repository.latest_decisions, 1)
    if not decisions:
        return {"free": None, "pro": None}
    listing, decision = decisions[0]
    return {
        "free": format_public_teaser(listing, "en"),
        "pro": format_card(listing, decision, "en"),
    }


@app.get("/content/market-pulse")
async def content_market_pulse() -> dict[str, Any]:
    report = await asyncio.to_thread(market_pulse, service.repository)
    return {
        "kind": report.kind,
        "period_from": report.period_from.isoformat(),
        "period_to": report.period_to.isoformat(),
        "sample_size": report.sample_size,
        "facts": report.facts,
        "provenance": report.provenance,
        "template_version": report.template_version,
    }


@app.get("/content/{kind}")
async def content_report(kind: str) -> dict[str, Any]:
    factories = {
        "price-drop": price_drop,
        "weekly-review": weekly_review,
        "deal-analysis": deal_analysis,
    }
    if kind == "poll":
        return audience_poll()
    factory = factories.get(kind)
    if factory is None:
        raise HTTPException(status_code=404, detail="Неизвестный формат контента")
    report = await asyncio.to_thread(factory, service.repository)
    return {
        "kind": report.kind,
        "period_from": report.period_from.isoformat(),
        "period_to": report.period_to.isoformat(),
        "sample_size": report.sample_size,
        "facts": report.facts,
        "provenance": report.provenance,
        "template_version": report.template_version,
    }


@app.post("/tma/auth")
async def tma_auth(request: TmaAuthRequest) -> dict[str, str]:
    try:
        principal = verify_telegram_init_data(request.init_data, settings.require_bot_token())
    except PermissionError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=401, detail="Telegram user отсутствует")
    import firebase_admin  # type: ignore[import-untyped]
    from firebase_admin import auth as firebase_auth

    try:
        firebase_admin.get_app()
    except ValueError:
        signer = os.getenv("FIREBASE_SIGNER_SERVICE_ACCOUNT", "").strip()
        options = {"serviceAccountId": signer} if signer else None
        firebase_admin.initialize_app(options=options)
    is_admin = principal.telegram_user_id in settings.telegram_admin_user_ids
    token = firebase_auth.create_custom_token(
        f"telegram:{principal.telegram_user_id}",
        {"telegram_user_id": principal.telegram_user_id, "admin": is_admin},
    )
    return {"firebase_custom_token": token.decode("utf-8")}


@app.get("/tma/feed")
async def tma_feed(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    subscription = await telegram_subscription_status(settings, principal.telegram_user_id)
    if not subscription.active:
        return {
            "owner": principal.telegram_user_id,
            "items": [],
            "is_admin": principal.admin,
            "is_pro": False,
        }
    user_settings = await asyncio.to_thread(
        service.repository.get_user_settings, principal.telegram_user_id
    )
    decisions = await current_market_snapshot()
    feed = []
    for listing, decision in select_publishable_decisions(decisions, settings, limit=50):
        evaluated = EvaluatedListing(
            listing=listing,
            content_hash=decision.content_hash or snapshot_hash(listing),
            decision=decision,
        )
        if user_settings is not None and not user_accepts(user_settings, evaluated):
            continue
        feed.append(
            {
                "listing": listing.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
            }
        )
    return {
        "owner": principal.telegram_user_id,
        "items": feed,
        "is_admin": principal.admin,
        "is_pro": True,
    }


@app.get("/tma/subscription")
async def tma_subscription(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Возвращает цену, membership entitlement и персональную referral-ссылку."""
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    subscription = await telegram_subscription_status(settings, principal.telegram_user_id)
    return {
        "plan": "pro" if subscription.active else "free",
        "active": subscription.active,
        "member_status": subscription.member_status,
        "price_aed": settings.pro_price_aed,
        "price_stars": settings.pro_price_stars,
        "period_days": 30,
        "subscription_url": settings.telegram_pro_subscription_url,
        "referral_url": (
            f"https://t.me/DubaiDealSniper111_bot?start=ref_{principal.telegram_user_id}"
        ),
    }


@app.get("/tma/outcomes")
async def tma_outcomes(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    outcomes = await asyncio.to_thread(service.repository.user_outcomes, principal.telegram_user_id)
    return {"items": [item.model_dump(mode="json") for item in outcomes]}


@app.post("/tma/outcomes")
async def tma_save_outcome(
    request: OutcomeRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    outcome = Outcome(user_id=principal.telegram_user_id, **request.model_dump())
    await asyncio.to_thread(service.repository.save_outcome, outcome)
    return {"ok": True}


@app.get("/tma/favorites")
async def tma_favorites(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    items = await asyncio.to_thread(service.repository.user_watchlist, principal.telegram_user_id)
    return {"items": items}


@app.post("/tma/favorites")
async def tma_save_favorite(
    request: FavoriteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    await asyncio.to_thread(
        service.repository.save_user_action,
        UserAction(
            user_id=principal.telegram_user_id,
            listing_id=request.listing_id,
            action="WATCH" if request.favorite else "REMOVED",
        ),
    )
    return {"ok": True}


@app.get("/tma/settings")
async def tma_settings(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    value = await asyncio.to_thread(
        service.repository.get_user_settings, principal.telegram_user_id
    ) or default_user_settings(principal.telegram_user_id)
    return value.model_dump(mode="json")


@app.post("/tma/settings")
async def tma_save_settings(
    request: TmaSettingsRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    current = await asyncio.to_thread(
        service.repository.get_user_settings, principal.telegram_user_id
    ) or default_user_settings(principal.telegram_user_id)
    payload = current.model_dump()
    payload.update(request.model_dump())
    value = UserSettings.model_validate(payload)
    await asyncio.to_thread(service.repository.save_user_settings, value)
    return value.model_dump(mode="json")


@app.get("/tma/searches")
async def tma_searches(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    items = await asyncio.to_thread(service.repository.user_searches, principal.telegram_user_id)
    return {"items": [item.model_dump(mode="json") for item in items]}


@app.post("/tma/searches")
async def tma_create_search(
    request: TmaSearchRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    current = await asyncio.to_thread(
        service.repository.get_user_settings, principal.telegram_user_id
    ) or default_user_settings(principal.telegram_user_id)
    parsed = parse_search(request.query, principal.telegram_user_id, current.language_code)
    search = build_saved_search(request.query, parsed).model_copy(update={"enabled": True})
    await asyncio.to_thread(service.repository.save_search, search)
    return {
        "search": search.model_dump(mode="json"),
        "recognized": parsed.recognized,
        "unknown": parsed.unknown,
    }


@app.post("/tma/searches/{search_id}")
async def tma_set_search_state(
    search_id: str,
    request: TmaSearchStateRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    principal = firebase_principal(authorization, require_admin=False)
    if principal.telegram_user_id is None:
        raise HTTPException(status_code=403, detail="Owner scope отсутствует")
    changed = await asyncio.to_thread(
        service.repository.set_search_enabled,
        principal.telegram_user_id,
        search_id,
        request.enabled,
    )
    if not changed:
        raise HTTPException(status_code=404, detail="Поиск не найден")
    return {"ok": True}


@app.get("/tma/summary")
async def tma_summary(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Показывает понятное состояние рынка без раскрытия административных данных."""
    firebase_principal(authorization, require_admin=False)
    decisions = await current_market_snapshot()
    action_counts: dict[str, int] = {}
    for _listing, decision in decisions:
        action_counts[decision.action.value] = action_counts.get(decision.action.value, 0) + 1
    source_switches = service.source_statuses()
    return {
        "listings": await asyncio.to_thread(service.repository.count_snapshots),
        "analyzed": len(decisions),
        "verified_market": sum(1 for _listing, decision in decisions if decision.market),
        "deals": sum(action_counts.get(action, 0) for action in ("CONTACT", "INSPECT", "WATCH")),
        "insufficient": action_counts.get("INSUFFICIENT_DATA", 0),
        "rejected": action_counts.get("REJECT", 0),
        "sources": len(source_switches),
        "sources_enabled": sum(source_switches.values()),
    }


@app.get("/tma/market-watch")
async def tma_market_watch(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Возвращает подтверждённые рыночные объекты, не выдавая их за сделки."""
    firebase_principal(authorization, require_admin=False)
    decisions = await current_market_snapshot()
    candidates = [item for item in decisions if item[1].market is not None]
    candidates.sort(key=lambda item: item[1].asking_price_aed / item[1].market.low_aed)
    return {
        "items": [
            {
                "listing": listing.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
            }
            for listing, decision in candidates[:50]
        ]
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    update_claimed: bool = Depends(telegram_update_lease),
) -> dict[str, bool]:
    """Принимает Telegram Update с проверкой webhook secret."""
    expected = settings.telegram_webhook_secret
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=403, detail="Неверный webhook secret")
    if not settings.delivery_enabled:
        return {"ok": True}
    if not update_claimed:
        return {"ok": True}

    message = update.get("message") or update.get("channel_post")
    if not isinstance(message, dict):
        return {"ok": True}
    sender = message.get("from", {})
    chat_id = effective_chat_id(message)
    user_id = sender.get("id")
    language = telegram_language(str(sender.get("language_code", "en")))

    def tr(russian: str, english: str) -> str:
        return localized(language, russian, english)

    raw_text = incoming_text(message)
    if raw_text is None:
        return {"ok": True}
    parts = raw_text.split()
    text = parts[0].split("@", maxsplit=1)[0].lower() if parts else ""
    arguments = parts[1:]
    if chat_id is None:
        return {"ok": True}

    admin_commands = {
        "/scan",
        "/source_scan",
        "/source_on",
        "/source_off",
        "/source_add",
        "/source_remove",
        "/sources",
        "/status",
    }
    if text in admin_commands and user_id not in settings.telegram_admin_user_ids:
        async with Bot(settings.require_bot_token()) as telegram_bot:
            bot = TelegramReplyClient(telegram_bot, message)
            await bot.send_message(chat_id=chat_id, text=tr("Недостаточно прав.", "Forbidden."))
        return {"ok": True}

    async with Bot(settings.require_bot_token()) as telegram_bot:
        bot = TelegramReplyClient(telegram_bot, message)
        if text == "/id":
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"ID чата: {chat_id}\nID пользователя: {user_id or '—'}",
                    f"Chat ID: {chat_id}\nUser ID: {user_id or '—'}",
                ),
            )
            return {"ok": True}
        if user_id is None:
            return {"ok": True}
        user_settings = await asyncio.to_thread(service.repository.get_user_settings, user_id)
        user_settings = user_settings or default_user_settings(user_id, language)
        if (
            text == "/start"
            and arguments
            and arguments[0].startswith("ref_")
            and user_settings.referred_by_user_id is None
        ):
            try:
                referrer_id = int(arguments[0].removeprefix("ref_"))
            except ValueError:
                referrer_id = user_id
            if referrer_id != user_id and referrer_id > 0:
                user_settings.referred_by_user_id = referrer_id
        if user_settings.language_code != language:
            user_settings.language_code = language
        await asyncio.to_thread(service.repository.save_user_settings, user_settings)
        if text in {"/start", "/help"}:
            await bot.send_message(
                chat_id=chat_id,
                text=welcome_text(),
                reply_markup=main_chat_keyboard(),
            )
        elif text == "/status":
            count = await asyncio.to_thread(service.repository.count_snapshots)
            health = await asyncio.to_thread(service.repository.source_health)
            lines = [
                tr(f"Сохранено версий: {count}", f"Stored versions: {count}"),
                "",
                tr("Последние запуски:", "Latest runs:"),
            ]
            for name in service.source_statuses():
                source_run = health.get(name, {})
                mark = "✅" if source_run.get("success") else "⚠️"
                fetched = source_run.get("fetched", "—")
                duration = source_run.get("duration_seconds", "—")
                lines.append(
                    tr(
                        f"{mark} {name}: {fetched} за {duration} с",
                        f"{mark} {name}: {fetched} in {duration} s",
                    )
                )
            await bot.send_message(chat_id=chat_id, text="\n".join(lines))
        elif text == "/scan":
            names = await launch_scan()
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"Сбор запущен в фоне: {', '.join(names)}. Результаты придут отдельно.",
                    f"Background scan started: {', '.join(names)}. Results will arrive separately.",
                ),
            )
        elif text == "/deals":
            decisions = await asyncio.to_thread(service.repository.latest_decisions, 500)
            recent_candidates = select_publishable_decisions(decisions, settings)
            if not recent_candidates:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr("Подходящих вариантов пока нет.", "No suitable cars yet."),
                )
            for listing, decision in recent_candidates:
                listing_id = f"{listing.source}:{listing.source_listing_id}"
                content_hash = decision.content_hash or snapshot_hash(listing)
                key = verification_key(listing.source, listing_id, content_hash, EXTRACTOR_VERSION)
                evidence = await asyncio.to_thread(
                    service.repository.get_verification_evidence, key
                )
                if evidence is None or not evidence_is_active(evidence):
                    continue
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_card(listing, decision, language),
                    parse_mode=ParseMode.HTML,
                )
        elif text == "/sources":
            await bot.send_message(
                chat_id=chat_id,
                text=format_sources(service, language),
            )
        elif text == "/settings":
            await bot.send_message(
                chat_id=chat_id,
                text=format_user_settings(user_settings, language),
            )
        elif text == "/find":
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr(
                        "Пример: /find Toyota Camry 2020-2023 бюджет 100000 "
                        "пробег 80000 GCC прибыль 5000 ROI 10",
                        "Example: /find Toyota Camry 2020-2023 budget 100000 "
                        "mileage 80000 GCC profit 5000 ROI 10",
                    ),
                )
                return {"ok": True}
            query = " ".join(arguments)
            parsed = parse_search(query, user_id, language)
            search = build_saved_search(query, parsed)
            await asyncio.to_thread(service.repository.save_search, search)
            recognized = "\n".join(f"• {item}" for item in parsed.recognized) or "—"
            unknown = ", ".join(parsed.unknown) or "—"
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"Распознано:\n{recognized}\n\nНе интерпретировано: {unknown}\n\n"
                    f"Подтвердите: /confirm_search {search.search_id}",
                    f"Recognized:\n{recognized}\n\nNot interpreted: {unknown}\n\n"
                    f"Confirm: /confirm_search {search.search_id}",
                ),
            )
        elif text == "/confirm_search":
            saved = bool(arguments) and await asyncio.to_thread(
                service.repository.set_search_enabled, user_id, arguments[0], True
            )
            await bot.send_message(
                chat_id=chat_id,
                text=tr("Поиск включён.", "Search enabled.")
                if saved
                else tr("Поиск не найден.", "Search not found."),
            )
        elif text == "/my_searches":
            searches = await asyncio.to_thread(service.repository.user_searches, user_id)
            lines = [
                f"{'✅' if item.enabled else '⏸'} {item.search_id}: {item.query_text}"
                for item in searches
            ]
            await bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines)
                if lines
                else tr("Сохранённых поисков нет.", "No saved searches."),
            )
        elif text == "/stop_search":
            stopped = bool(arguments) and await asyncio.to_thread(
                service.repository.set_search_enabled, user_id, arguments[0], False
            )
            await bot.send_message(
                chat_id=chat_id,
                text=tr("Поиск остановлен.", "Search stopped.")
                if stopped
                else tr("Поиск не найден.", "Search not found."),
            )
        elif text in {"/set_budget", "/set_profit", "/set_roi", "/set_makes"}:
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr("После команды укажите значение.", "Enter a value after the command."),
                )
                return {"ok": True}
            value = user_settings
            try:
                if text == "/set_budget":
                    value.max_budget_aed = Decimal(arguments[0])
                elif text == "/set_profit":
                    value.min_profit_aed = Decimal(arguments[0])
                elif text == "/set_roi":
                    value.min_roi_percent = Decimal(arguments[0])
                else:
                    value.makes = [
                        item.strip().title()
                        for item in " ".join(arguments).split(",")
                        if item.strip()
                    ]
                value = UserSettings.model_validate(value.model_dump())
            except (InvalidOperation, ValueError):
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr("Некорректное значение настройки.", "Invalid setting value."),
                )
                return {"ok": True}
            await asyncio.to_thread(service.repository.save_user_settings, value)
            await bot.send_message(
                chat_id=chat_id,
                text=format_user_settings(value, language),
            )
        elif text in {"/watch", "/contacted", "/inspect", "/reject"}:
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr(
                        "Укажите ID объявления после команды.",
                        "Enter the listing ID after the command.",
                    ),
                )
                return {"ok": True}
            action_name = {
                "/watch": "WATCH",
                "/contacted": "CONTACTED",
                "/inspect": "INSPECT",
                "/reject": "REJECT",
            }[text]
            await asyncio.to_thread(
                service.repository.save_user_action,
                UserAction(user_id=user_id, listing_id=arguments[0], action=action_name),
            )
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"Статус сохранён: {action_name}.",
                    f"Status saved: {action_name}.",
                ),
            )
        elif text == "/watchlist":
            items = await asyncio.to_thread(service.repository.user_watchlist, user_id)
            message_text = (
                tr("Наблюдаемые объявления:\n", "Watched listings:\n") + "\n".join(items[:20])
                if items
                else tr("Список наблюдения пуст.", "The watchlist is empty.")
            )
            await bot.send_message(chat_id=chat_id, text=message_text)
        elif text in {"/source_on", "/source_add", "/source_off", "/source_remove"}:
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr(
                        "Укажите источник. Пример: /source_on cars24",
                        "Enter a source. Example: /source_on cars24",
                    ),
                )
                return {"ok": True}
            enabled = text in {"/source_on", "/source_add"}
            try:
                await asyncio.to_thread(service.set_source_enabled, arguments[0], enabled)
            except ValueError:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_sources(service, language),
                )
                return {"ok": True}
            action = tr("включён", "enabled") if enabled else tr("отключён", "disabled")
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"Источник {arguments[0].casefold()} {action}.",
                    f"Source {arguments[0].casefold()} {action}.",
                )
                + f"\n\n{format_sources(service, language)}",
            )
        elif text == "/source_scan":
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr(
                        "Укажите источник. Пример: /source_scan cars24",
                        "Enter a source. Example: /source_scan cars24",
                    ),
                )
                return {"ok": True}
            source_name = arguments[0].casefold()
            try:
                names = await launch_scan(source_name)
            except (RuntimeError, ValueError) as error:
                await bot.send_message(
                    chat_id=chat_id,
                    text=tr(f"Ошибка источника: {error}", f"Source error: {error}"),
                )
                return {"ok": True}
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"Фоновый сбор запущен: {', '.join(names)}.",
                    f"Background scan started: {', '.join(names)}.",
                ),
            )
        else:
            if raw_text and not raw_text.startswith("/") and user_id is not None:
                intent = classify_chat_intent(raw_text)
                if intent is ChatIntent.GREETING:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=welcome_text(),
                        reply_markup=main_chat_keyboard(),
                    )
                elif intent is ChatIntent.HELP:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=help_text(),
                        reply_markup=main_chat_keyboard(),
                    )
                elif intent is ChatIntent.FIND_CAR:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=search_prompt_text(),
                        reply_markup=main_chat_keyboard(),
                    )
                elif intent is ChatIntent.NEWS:
                    news = await news_client.latest()
                    if news:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=format_news(news),
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                            reply_markup=main_chat_keyboard(),
                        )
                    else:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "The automotive news feed is temporarily unavailable. "
                                "I will not invent a headline—please try again shortly."
                            ),
                            reply_markup=main_chat_keyboard(),
                        )
                elif intent is ChatIntent.UPGRADE:
                    subscription = await telegram_subscription_status(settings, user_id)
                    await bot.send_message(
                        chat_id=chat_id,
                        text=pro_subscription_text(subscription.active),
                        parse_mode=ParseMode.HTML,
                        reply_markup=pro_subscription_keyboard(),
                    )
                elif intent is ChatIntent.MARKET:
                    market_items = await current_market_snapshot()
                    market_decisions = [decision for _, decision in market_items]
                    with_market = sum(decision.market is not None for decision in market_decisions)
                    opportunities = sum(
                        decision.action.value in {"CONTACT", "INSPECT"}
                        for decision in market_decisions
                    )
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "<b>Dubai verified market overview</b>\n\n"
                            f"Processed current listings: {len(market_decisions):,}\n"
                            f"Listings with a comparable market: {with_market:,}\n"
                            f"Current CONTACT/INSPECT opportunities: {opportunities:,}\n\n"
                            "Open the application to explore verified market cards."
                        ),
                        parse_mode=ParseMode.HTML,
                        reply_markup=main_chat_keyboard(),
                    )
                elif intent is ChatIntent.SOURCES:
                    statuses = service.source_statuses()
                    enabled_sources = [name for name, active in statuses.items() if active]
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "Current listing sources: " + ", ".join(enabled_sources) + ".\n"
                            "Every published price must pass detail-page verification."
                        ),
                        reply_markup=main_chat_keyboard(),
                    )
                else:
                    parsed = parse_search(raw_text, user_id, language)
                    if parsed.recognized:
                        search = build_saved_search(raw_text, parsed).model_copy(
                            update={"enabled": True}
                        )
                        await asyncio.to_thread(service.repository.save_search, search)
                        recognized = "\n".join(f"• {item}" for item in parsed.recognized)
                        await bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"Your search is active:\n{recognized}\n\n"
                                "I will notify you when a matching verified car appears."
                            ),
                            reply_markup=main_chat_keyboard(),
                        )
                    else:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=help_text(),
                            reply_markup=main_chat_keyboard(),
                        )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=help_text(),
                    reply_markup=main_chat_keyboard(),
                )
    return {"ok": True}


@app.post("/tasks/process-listing")
async def process_listing_task(
    task: ProcessingTask,
    x_internal_task_secret: str | None = Header(default=None),
    x_cloudtasks_taskname: str | None = Header(default=None),
) -> dict[str, bool]:
    """Рассчитывает одну версию и ставит подходящую карточку в очередь доставки."""
    require_internal_task(x_internal_task_secret, x_cloudtasks_taskname)
    if task.engine_version != service.decision_engine.version:
        return {"ok": True}
    evaluated = await service.process_listing(task.listing_id, task.content_hash)
    if evaluated is None or not is_publishable(evaluated.decision, settings):
        return {"ok": True}
    current_decision_id = evaluated.decision.decision_id or task.listing_id
    vehicle_id = evaluated.decision.vehicle_id or task.listing_id
    event_id = publication_event_id(
        decision_id_value=current_decision_id,
        vehicle_id=vehicle_id,
        event_type="deal-candidate",
    )
    await asyncio.to_thread(
        service.repository.save_publication_event,
        PublicationEvent(
            publication_event_id=event_id,
            decision_id=current_decision_id,
            vehicle_id=vehicle_id,
            event_type="deal-candidate",
            template_version="deal/v1",
        ),
    )
    targets: dict[str, tuple[str, str]] = {}
    for user_id in settings.telegram_allowed_user_ids:
        user_settings = await asyncio.to_thread(
            service.repository.get_user_settings,
            user_id,
        )
        effective_settings = user_settings or default_user_settings(user_id)
        if user_accepts(effective_settings, evaluated):
            targets[str(user_id)] = (
                telegram_language(effective_settings.language_code),
                "personal-pro/v1"
                if effective_settings.tariff.casefold() == "pro"
                else "personal-free/v1",
            )
    active_searches = await asyncio.to_thread(service.repository.active_searches)
    for saved_search in active_searches:
        if user_accepts(saved_search.filters, evaluated):
            template = (
                "personal-pro/v1"
                if saved_search.filters.tariff.casefold() == "pro"
                else "personal-free/v1"
            )
            targets[str(saved_search.user_id)] = (
                telegram_language(saved_search.filters.language_code),
                template,
            )
    if settings.telegram_pro_channel_id:
        targets[settings.telegram_pro_channel_id] = ("en", "pro/v1")
    if settings.telegram_channel_id:
        targets[settings.telegram_channel_id] = ("en", "free/v1")
    dispatcher = CloudTaskDispatcher(settings)
    for target_id, (target_language, template_version) in targets.items():
        card = (
            format_public_teaser(evaluated.listing, target_language)
            if template_version in {"free/v1", "personal-free/v1"}
            else format_card(evaluated.listing, evaluated.decision, target_language)
        )
        stable_delivery_id = delivery_id(
            decision_id_value=current_decision_id,
            recipient_id=target_id,
            template_version=template_version,
            format_name="telegram",
        )
        delivery_payload: dict[str, object] = {
            "delivery_id": stable_delivery_id,
            "decision_id": current_decision_id,
            "target_id": target_id,
            "listing_id": task.listing_id,
            "content_hash": task.content_hash,
            "text": card,
            "engine_version": evaluated.decision.engine_version,
            "template_version": template_version,
            "format": "telegram",
        }
        if template_version in {"free/v1", "personal-free/v1"}:
            delivery_payload["image_url"] = settings.free_teaser_image_url
        elif evaluated.listing.image_urls:
            delivery_payload["image_url"] = str(evaluated.listing.image_urls[0])
        await asyncio.to_thread(
            service.repository.put_outbox,
            OutboxRecord(
                delivery_id=stable_delivery_id,
                decision_id=current_decision_id,
                recipient=target_id,
                template_version=template_version,
                format="telegram",
                payload=delivery_payload,
            ),
        )
        await dispatcher.enqueue_delivery(delivery_payload)
    return {"ok": True}


@app.post("/tasks/deliver-telegram")
async def deliver_telegram_task(
    task: DeliveryTask,
    x_internal_task_secret: str | None = Header(default=None),
    x_cloudtasks_taskname: str | None = Header(default=None),
) -> dict[str, bool]:
    """Доставляет Telegram-карточку ровно один раз на получателя и версию."""
    require_internal_task(x_internal_task_secret, x_cloudtasks_taskname)
    if not settings.delivery_enabled:
        return {"ok": True}
    if task.engine_version != service.decision_engine.version:
        return {"ok": True}
    latest = await asyncio.to_thread(
        service.repository.get_snapshot, task.listing_id, task.content_hash
    )
    current = await asyncio.to_thread(
        service.repository.is_current_snapshot, task.listing_id, task.content_hash
    )
    if latest is None or not current or snapshot_hash(latest) != task.content_hash:
        return {"ok": True}
    key = verification_key(latest.source, task.listing_id, task.content_hash, EXTRACTOR_VERSION)
    evidence = await asyncio.to_thread(service.repository.get_verification_evidence, key)
    if evidence is None or not evidence_is_active(evidence):
        return {"ok": True}
    lease_owner = os.getenv("K_REVISION", "local-delivery")
    claimed = await asyncio.to_thread(
        service.repository.claim_outbox, task.delivery_id, lease_owner
    )
    if claimed is None:
        return {"ok": True}
    try:
        async with Bot(settings.require_bot_token()) as bot:
            if task.image_url:
                sent = await bot.send_photo(
                    chat_id=task.target_id,
                    photo=task.image_url,
                    caption=task.text,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await bot.send_message(
                    chat_id=task.target_id,
                    text=task.text,
                    parse_mode=ParseMode.HTML,
                )
    except (TimedOut, NetworkError) as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.UNKNOWN,
            error=f"{type(error).__name__}: {error}",
        )
        return {"ok": True}
    except Exception as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.FAILED,
            error=f"{type(error).__name__}: {error}",
        )
        raise
    await asyncio.to_thread(
        service.repository.update_outbox,
        task.delivery_id,
        OutboxState.SENT,
        telegram_message_id=str(sent.message_id),
    )
    return {"ok": True}


@app.post("/tasks/deliver-content")
async def deliver_content_task(
    task: ContentDeliveryTask,
    x_internal_task_secret: str | None = Header(default=None),
    x_cloudtasks_taskname: str | None = Header(default=None),
) -> dict[str, bool]:
    require_internal_task(x_internal_task_secret, x_cloudtasks_taskname)
    if not settings.delivery_enabled:
        return {"ok": True}
    claimed = await asyncio.to_thread(
        service.repository.claim_outbox,
        task.delivery_id,
        os.getenv("K_REVISION", "local-content-delivery"),
    )
    if claimed is None:
        return {"ok": True}
    try:
        async with Bot(settings.require_bot_token()) as bot:
            if task.image_url:
                sent = await bot.send_photo(
                    chat_id=task.target_id,
                    photo=task.image_url,
                    caption=task.text,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await bot.send_message(
                    chat_id=task.target_id,
                    text=task.text,
                    parse_mode=ParseMode.HTML,
                )
    except (TimedOut, NetworkError) as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.UNKNOWN,
            error=f"{type(error).__name__}: {error}",
        )
        return {"ok": True}
    except Exception as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.FAILED,
            error=f"{type(error).__name__}: {error}",
        )
        raise
    await asyncio.to_thread(
        service.repository.update_outbox,
        task.delivery_id,
        OutboxState.SENT,
        telegram_message_id=str(sent.message_id),
    )
    return {"ok": True}


@app.post("/tasks/deliver-whatsapp")
async def deliver_whatsapp_task(
    task: WhatsAppDeliveryTask,
    x_internal_task_secret: str | None = Header(default=None),
    x_cloudtasks_taskname: str | None = Header(default=None),
) -> dict[str, bool]:
    """Официальный Meta Cloud API path; при отсутствии credentials всегда fail-closed."""
    require_internal_task(x_internal_task_secret, x_cloudtasks_taskname)
    if not settings.delivery_enabled or not settings.whatsapp_enabled:
        return {"ok": True}
    claimed = await asyncio.to_thread(
        service.repository.claim_outbox,
        task.delivery_id,
        os.getenv("K_REVISION", "local-whatsapp-delivery"),
    )
    if claimed is None:
        return {"ok": True}
    adapter = WhatsAppAdapter(
        WhatsAppConfig(
            enabled=settings.whatsapp_enabled,
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
            api_version=settings.whatsapp_api_version,
        )
    )
    try:
        message_id = await adapter.send_template(
            task.recipient,
            task.template_name,
            task.language_code,
            task.components,
            opted_in=task.opted_in,
        )
    except (TimeoutException, TransportError) as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.UNKNOWN,
            error=f"{type(error).__name__}: {error}",
        )
        return {"ok": True}
    except Exception as error:
        await asyncio.to_thread(
            service.repository.update_outbox,
            task.delivery_id,
            OutboxState.FAILED,
            error=f"{type(error).__name__}: {error}",
        )
        raise
    await asyncio.to_thread(
        service.repository.update_outbox,
        task.delivery_id,
        OutboxState.SENT,
        provider_message_id=message_id,
    )
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled_error(_request: Any, error: Exception) -> Any:
    """Логирует ошибку и возвращает контролируемый HTTP-ответ."""
    logger.exception("Необработанная ошибка Cloud Run API", exc_info=error)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"ok": False})

"""Cloud Run HTTP API и Telegram webhook."""

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telegram import Bot
from telegram.constants import ParseMode

from src.bot import (
    format_card,
    format_sources,
    is_publishable,
    localized,
    select_publishable_decisions,
    telegram_language,
)
from src.cloud_jobs import CloudJobLauncher
from src.config import Settings
from src.domain.models import UserAction, UserSettings
from src.service import DealService, EvaluatedListing
from src.tasks import CloudTaskDispatcher

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
settings = Settings.from_env()
service = DealService.from_settings(settings)
app = FastAPI(title="Dubai Deal Sniper", version="0.5.0")


class ProcessingTask(BaseModel):
    listing_id: str
    content_hash: str
    engine_version: str


class DeliveryTask(BaseModel):
    target_id: str
    listing_id: str
    content_hash: str
    text: str


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
    return not allowed_makes or (item.listing.make or "").casefold() in allowed_makes


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка процесса для Cloud Run."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Проверка обязательной production-конфигурации."""
    if not settings.telegram_bot_token or not settings.google_cloud_project:
        raise HTTPException(status_code=503, detail="Обязательная конфигурация отсутствует")
    return {"status": "ready"}


@app.get("/version")
async def version() -> dict[str, str]:
    """Версия API и детерминированного движка для smoke checks."""
    return {"api": "0.5.0", "decision_engine": service.decision_engine.version}


@app.post("/telegram/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Принимает Telegram Update с проверкой webhook secret."""
    expected = settings.telegram_webhook_secret
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=403, detail="Неверный webhook secret")

    update_id = update.get("update_id")
    if isinstance(update_id, int):
        claimed = await asyncio.to_thread(service.repository.claim_telegram_update, update_id)
        if not claimed:
            return {"ok": True}

    message = update.get("message") or update.get("channel_post")
    if not isinstance(message, dict):
        return {"ok": True}
    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_id = chat.get("id")
    user_id = sender.get("id")
    language = telegram_language(str(sender.get("language_code", "en")))

    def tr(russian: str, english: str) -> str:
        return localized(language, russian, english)

    raw_text = str(message.get("text", "")).strip()
    parts = raw_text.split()
    text = parts[0].split("@", maxsplit=1)[0].lower() if parts else ""
    arguments = parts[1:]
    if chat_id is None:
        return {"ok": True}

    async with Bot(settings.require_bot_token()) as bot:
        if text == "/id":
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    f"ID чата: {chat_id}\nID пользователя: {user_id or '—'}",
                    f"Chat ID: {chat_id}\nUser ID: {user_id or '—'}",
                ),
            )
            return {"ok": True}
        if user_id not in settings.telegram_allowed_user_ids:
            await bot.send_message(
                chat_id=chat_id,
                text=tr("Доступ к боту не настроен.", "Bot access is not configured."),
            )
            return {"ok": True}
        user_settings = await asyncio.to_thread(service.repository.get_user_settings, user_id)
        user_settings = user_settings or default_user_settings(user_id, language)
        if user_settings.language_code != language:
            user_settings.language_code = language
        await asyncio.to_thread(service.repository.save_user_settings, user_settings)
        if text in {"/start", "/help"}:
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    "Dubai Deal Sniper работает в Google Cloud.\n\n"
                    "/scan — получить объявления и выполнить расчёт\n"
                    "/deals — показать последние подходящие варианты\n"
                    "/status — показать состояние хранилища\n"
                    "/sources — управление источниками\n"
                    "/settings — персональные фильтры\n"
                    "/watchlist — сохранённые автомобили",
                    "Dubai Deal Sniper runs in Google Cloud.\n\n"
                    "/scan — fetch listings and calculate deals\n"
                    "/deals — show the latest suitable cars\n"
                    "/status — show system status\n"
                    "/sources — manage sources\n"
                    "/settings — personal filters\n"
                    "/watchlist — saved cars",
                ),
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
            await bot.send_message(
                chat_id=chat_id,
                text=tr(
                    "Используйте /start для списка команд.",
                    "Use /start to see the command list.",
                ),
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
    targets: dict[str, str] = {}
    for user_id in settings.telegram_allowed_user_ids:
        user_settings = await asyncio.to_thread(
            service.repository.get_user_settings,
            user_id,
        )
        if user_accepts(user_settings or default_user_settings(user_id), evaluated):
            targets[str(user_id)] = telegram_language(
                (user_settings or default_user_settings(user_id)).language_code
            )
    delivery_channel_id = settings.telegram_pro_channel_id or settings.telegram_channel_id
    if delivery_channel_id:
        targets[delivery_channel_id] = "en"
    dispatcher = CloudTaskDispatcher(settings)
    for target_id, target_language in targets.items():
        card = format_card(evaluated.listing, evaluated.decision, target_language)
        await dispatcher.enqueue_delivery(
            {
                "target_id": target_id,
                "listing_id": task.listing_id,
                "content_hash": task.content_hash,
                "text": card,
            }
        )
    return {"ok": True}


@app.post("/tasks/deliver-telegram")
async def deliver_telegram_task(
    task: DeliveryTask,
    x_internal_task_secret: str | None = Header(default=None),
    x_cloudtasks_taskname: str | None = Header(default=None),
) -> dict[str, bool]:
    """Доставляет Telegram-карточку ровно один раз на получателя и версию."""
    require_internal_task(x_internal_task_secret, x_cloudtasks_taskname)
    if await asyncio.to_thread(
        service.repository.notification_sent,
        task.target_id,
        task.listing_id,
        task.content_hash,
    ):
        return {"ok": True}
    async with Bot(settings.require_bot_token()) as bot:
        await bot.send_message(
            chat_id=task.target_id,
            text=task.text,
            parse_mode=ParseMode.HTML,
        )
    await asyncio.to_thread(
        service.repository.mark_notification_sent,
        task.target_id,
        task.listing_id,
        task.content_hash,
    )
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled_error(_request: Any, error: Exception) -> Any:
    """Логирует ошибку и возвращает контролируемый HTTP-ответ."""
    logger.exception("Необработанная ошибка Cloud Run API", exc_info=error)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"ok": False})

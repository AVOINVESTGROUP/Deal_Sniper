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
    select_publishable_decisions,
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
app = FastAPI(title="Dubai Deal Sniper", version="0.3.7")


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
        [source_name]
        if source_name
        else [name for name, enabled in statuses.items() if enabled]
    )
    names = [name for name in names if name in statuses and statuses[name]]
    if not names:
        raise ValueError("Нет включённых источников")
    launcher = CloudJobLauncher(settings)
    await launcher.run_collectors(names)
    return names


def default_user_settings(user_id: int) -> UserSettings:
    return UserSettings(
        user_id=user_id,
        min_profit_aed=settings.target_profit_aed,
        min_roi_percent=settings.min_roi_percent,
    )


def format_user_settings(value: UserSettings) -> str:
    budget = f"{value.max_budget_aed:,.0f} AED" if value.max_budget_aed else "без лимита"
    makes = ", ".join(value.makes) if value.makes else "все марки"
    return (
        "Ваши настройки:\n"
        f"Бюджет: {budget}\n"
        f"Минимальная прибыль: {value.min_profit_aed:,.0f} AED\n"
        f"Минимальный ROI: {value.min_roi_percent}%\n"
        f"Марки: {makes}\n\n"
        "/set_budget 150000\n/set_profit 7000\n/set_roi 12\n"
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
    return {"api": "0.3.7", "decision_engine": service.decision_engine.version}


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
    raw_text = str(message.get("text", "")).strip()
    parts = raw_text.split()
    text = parts[0].split("@", maxsplit=1)[0].lower() if parts else ""
    arguments = parts[1:]
    if chat_id is None:
        return {"ok": True}

    async with Bot(settings.require_bot_token()) as bot:
        if text == "/id":
            await bot.send_message(chat_id=chat_id, text=f"Ваш Telegram user ID: {user_id}")
            return {"ok": True}
        if user_id not in settings.telegram_allowed_user_ids:
            await bot.send_message(chat_id=chat_id, text="Доступ к боту не настроен.")
            return {"ok": True}
        if text in {"/start", "/help"}:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Dubai Deal Sniper работает в Google Cloud.\n\n"
                    "/scan — получить объявления и выполнить расчёт\n"
                    "/deals — показать последние подходящие варианты\n"
                    "/status — показать состояние хранилища\n"
                    "/sources — управление источниками\n"
                    "/settings — персональные фильтры\n"
                    "/watchlist — сохранённые автомобили"
                ),
            )
        elif text == "/status":
            count = await asyncio.to_thread(service.repository.count_snapshots)
            health = await asyncio.to_thread(service.repository.source_health)
            lines = [f"Сохранено версий: {count}", "", "Последние запуски:"]
            for name in service.source_statuses():
                source_run = health.get(name, {})
                mark = "✅" if source_run.get("success") else "⚠️"
                fetched = source_run.get("fetched", "—")
                duration = source_run.get("duration_seconds", "—")
                lines.append(f"{mark} {name}: {fetched} за {duration} с")
            await bot.send_message(chat_id=chat_id, text="\n".join(lines))
        elif text == "/scan":
            names = await launch_scan()
            await bot.send_message(
                chat_id=chat_id,
                text=f"Сбор запущен в фоне: {', '.join(names)}. Результаты придут отдельно.",
            )
        elif text == "/deals":
            decisions = await asyncio.to_thread(service.repository.latest_decisions, 500)
            recent_candidates = select_publishable_decisions(decisions, settings)
            if not recent_candidates:
                await bot.send_message(chat_id=chat_id, text="Подходящих вариантов пока нет.")
            for listing, decision in recent_candidates:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_card(listing, decision),
                    parse_mode=ParseMode.HTML,
                )
        elif text == "/sources":
            await bot.send_message(chat_id=chat_id, text=format_sources(service))
        elif text == "/settings":
            value = await asyncio.to_thread(service.repository.get_user_settings, user_id)
            await bot.send_message(
                chat_id=chat_id,
                text=format_user_settings(value or default_user_settings(user_id)),
            )
        elif text in {"/set_budget", "/set_profit", "/set_roi", "/set_makes"}:
            if not arguments:
                await bot.send_message(chat_id=chat_id, text="После команды укажите значение.")
                return {"ok": True}
            value = await asyncio.to_thread(service.repository.get_user_settings, user_id)
            value = value or default_user_settings(user_id)
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
                await bot.send_message(chat_id=chat_id, text="Некорректное значение настройки.")
                return {"ok": True}
            await asyncio.to_thread(service.repository.save_user_settings, value)
            await bot.send_message(chat_id=chat_id, text=format_user_settings(value))
        elif text in {"/watch", "/contacted", "/inspect", "/reject"}:
            if not arguments:
                await bot.send_message(chat_id=chat_id, text="Укажите ID объявления после команды.")
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
            await bot.send_message(chat_id=chat_id, text=f"Статус сохранён: {action_name}.")
        elif text == "/watchlist":
            items = await asyncio.to_thread(service.repository.user_watchlist, user_id)
            message_text = (
                "Наблюдаемые объявления:\n" + "\n".join(items[:20])
                if items
                else "Список наблюдения пуст."
            )
            await bot.send_message(chat_id=chat_id, text=message_text)
        elif text in {"/source_on", "/source_add", "/source_off", "/source_remove"}:
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Укажите источник. Пример: /source_on cars24",
                )
                return {"ok": True}
            enabled = text in {"/source_on", "/source_add"}
            try:
                await asyncio.to_thread(service.set_source_enabled, arguments[0], enabled)
            except ValueError:
                await bot.send_message(chat_id=chat_id, text=format_sources(service))
                return {"ok": True}
            action = "включён" if enabled else "отключён"
            await bot.send_message(
                chat_id=chat_id,
                text=f"Источник {arguments[0].casefold()} {action}.\n\n{format_sources(service)}",
            )
        elif text == "/source_scan":
            if not arguments:
                await bot.send_message(
                    chat_id=chat_id,
                    text="Укажите источник. Пример: /source_scan cars24",
                )
                return {"ok": True}
            source_name = arguments[0].casefold()
            try:
                names = await launch_scan(source_name)
            except (RuntimeError, ValueError) as error:
                await bot.send_message(chat_id=chat_id, text=f"Ошибка источника: {error}")
                return {"ok": True}
            await bot.send_message(
                chat_id=chat_id,
                text=f"Фоновый сбор запущен: {', '.join(names)}.",
            )
        else:
            await bot.send_message(chat_id=chat_id, text="Используйте /start для списка команд.")
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
    targets: set[str] = set()
    for user_id in settings.telegram_allowed_user_ids:
        user_settings = await asyncio.to_thread(
            service.repository.get_user_settings,
            user_id,
        )
        if user_accepts(user_settings or default_user_settings(user_id), evaluated):
            targets.add(str(user_id))
    if settings.telegram_channel_id:
        targets.add(settings.telegram_channel_id)
    dispatcher = CloudTaskDispatcher(settings)
    card = format_card(evaluated.listing, evaluated.decision)
    for target_id in targets:
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

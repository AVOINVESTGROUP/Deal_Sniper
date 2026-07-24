"""Cloud Run HTTP API и Telegram webhook."""

import asyncio
import logging
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from telegram import Bot
from telegram.constants import ParseMode

from src.bot import format_card, format_sources
from src.config import Settings
from src.domain.models import DecisionAction
from src.service import DealService

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
settings = Settings.from_env()
service = DealService.from_settings(settings)
app = FastAPI(title="Dubai Deal Sniper", version="0.2.0")


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
                    "/sources — управление источниками"
                ),
            )
        elif text == "/status":
            count = await asyncio.to_thread(service.repository.count_snapshots)
            await bot.send_message(chat_id=chat_id, text=f"Сохранено версий: {count}")
        elif text == "/scan":
            await bot.send_message(chat_id=chat_id, text="Получаю свежие объявления…")
            report = await service.scan()
            await bot.send_message(chat_id=chat_id, text=report.summary())
            candidates = [
                item
                for item in report.decisions
                if item.decision.action in {DecisionAction.CONTACT, DecisionAction.INSPECT}
            ][:5]
            for item in candidates:
                await bot.send_message(
                    chat_id=chat_id,
                    text=format_card(item.listing, item.decision),
                    parse_mode=ParseMode.HTML,
                )
        elif text == "/deals":
            decisions = await asyncio.to_thread(service.repository.latest_decisions, 20)
            recent_candidates = [
                item
                for item in decisions
                if item[1].action in {DecisionAction.CONTACT, DecisionAction.INSPECT}
            ][:5]
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
            await bot.send_message(chat_id=chat_id, text=f"Проверяю источник {source_name}…")
            try:
                report = await service.scan(source_name)
            except (RuntimeError, ValueError) as error:
                await bot.send_message(chat_id=chat_id, text=f"Ошибка источника: {error}")
                return {"ok": True}
            await bot.send_message(chat_id=chat_id, text=f"{source_name}: {report.summary()}")
        else:
            await bot.send_message(chat_id=chat_id, text="Используйте /start для списка команд.")
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled_error(_request: Any, error: Exception) -> Any:
    """Логирует ошибку и возвращает контролируемый HTTP-ответ."""
    logger.exception("Необработанная ошибка Cloud Run API", exc_info=error)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=500, content={"ok": False})

"""Нативная монетизация Pro через Telegram Stars subscription link."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from src.config import Settings
from src.runtime_config import SUBSCRIPTION_PERIOD_SECONDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionStatus:
    """Проверенный статус доступа пользователя к Pro-каналу."""

    active: bool
    member_status: str


async def telegram_subscription_status(
    settings: Settings,
    user_id: int,
) -> SubscriptionStatus:
    """Проверяет entitlement по фактическому членству, при ошибке закрывает доступ."""
    if not settings.telegram_pro_channel_id:
        return SubscriptionStatus(active=False, member_status="not_configured")
    try:
        async with Bot(settings.require_bot_token()) as bot:
            member = await bot.get_chat_member(settings.telegram_pro_channel_id, user_id)
    except TelegramError as error:
        logger.warning("Не удалось проверить Pro membership: %s", type(error).__name__)
        return SubscriptionStatus(active=False, member_status="unavailable")
    active_statuses = {
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    }
    return SubscriptionStatus(
        active=member.status in active_statuses,
        member_status=str(member.status),
    )


async def telegram_subscription_metrics(settings: Settings) -> dict[str, int | str | None]:
    """Возвращает безопасные агрегаты для закрытой панели оператора."""
    if not settings.telegram_pro_channel_id:
        return {"channel_members": 0, "star_balance": None, "status": "not_configured"}
    try:
        async with Bot(settings.require_bot_token()) as bot:
            members = await bot.get_chat_member_count(settings.telegram_pro_channel_id)
            balance = await bot.get_my_star_balance()
        return {
            "channel_members": members,
            "star_balance": int(balance.amount),
            "status": "available",
        }
    except TelegramError as error:
        logger.warning("Не удалось получить subscription metrics: %s", type(error).__name__)
        return {"channel_members": 0, "star_balance": None, "status": "unavailable"}


async def create_telegram_subscription_link(
    settings: Settings,
    *,
    price_stars: int,
    name: str,
) -> str:
    """Создаёт новую 30-дневную Stars-ссылку после строгой проверки параметров."""
    if not settings.telegram_pro_channel_id:
        raise ValueError("TELEGRAM_PRO_CHANNEL_ID не настроен")
    if price_stars < 1 or price_stars > 10_000:
        raise ValueError("Цена Telegram должна быть от 1 до 10 000 Stars")
    safe_name = name.strip()[:32]
    if not safe_name:
        raise ValueError("Имя subscription link обязательно")
    try:
        async with Bot(settings.require_bot_token()) as bot:
            link = await bot.create_chat_subscription_invite_link(
                chat_id=settings.telegram_pro_channel_id,
                subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
                subscription_price=price_stars,
                name=safe_name,
            )
    except TelegramError as error:
        logger.warning("Не удалось создать Telegram subscription link: %s", type(error).__name__)
        raise RuntimeError("Telegram не создал новую subscription link") from error
    invite_link = str(link.invite_link).strip()
    if not invite_link.startswith(("https://t.me/", "https://telegram.me/")):
        raise RuntimeError("Telegram вернул некорректную subscription link")
    return invite_link

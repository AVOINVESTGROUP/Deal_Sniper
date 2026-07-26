"""Нативная монетизация Pro через Telegram Stars subscription link."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from telegram import Bot
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from src.config import Settings

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

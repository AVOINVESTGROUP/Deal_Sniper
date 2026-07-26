"""Детерминированная маршрутизация естественного диалога Telegram."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ChatIntent(StrEnum):
    """Поддерживаемые намерения обычного пользовательского сообщения."""

    GREETING = "greeting"
    FIND_CAR = "find_car"
    NEWS = "news"
    MARKET = "market"
    SOURCES = "sources"
    HELP = "help"
    UPGRADE = "upgrade"
    UNKNOWN = "unknown"


def effective_chat_id(message: dict[str, Any]) -> int | str | None:
    """Возвращает новый ID supergroup, если Telegram прислал событие миграции."""
    migrated = message.get("migrate_to_chat_id")
    if isinstance(migrated, int):
        return migrated
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    value = chat.get("id")
    return value if isinstance(value, (int, str)) else None


def incoming_text(message: dict[str, Any]) -> str | None:
    """Возвращает пользовательский текст и отбрасывает служебные Telegram-события."""
    value = message.get("text")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def classify_chat_intent(text: str) -> ChatIntent:
    """Определяет намерение без LLM и без создания несуществующих фактов."""
    normalized = " ".join(text.casefold().strip().split())
    if not normalized:
        return ChatIntent.HELP

    exact_greetings = {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "привет",
        "здравствуйте",
    }
    if normalized in exact_greetings:
        return ChatIntent.GREETING
    if any(token in normalized for token in ("news", "headline", "latest update", "новост")):
        return ChatIntent.NEWS
    if any(
        token in normalized
        for token in ("upgrade", "subscribe", "subscription", "pro access", "buy pro")
    ):
        return ChatIntent.UPGRADE
    if any(
        token in normalized
        for token in ("market overview", "market status", "market pulse", "обзор рынка")
    ):
        return ChatIntent.MARKET
    if any(token in normalized for token in ("source", "where do you get", "источник")):
        return ChatIntent.SOURCES
    if any(
        token in normalized
        for token in ("find a car", "car search", "looking for a car", "подбери", "найди авто")
    ):
        return ChatIntent.FIND_CAR
    if any(
        token in normalized
        for token in ("help", "how does", "what can you", "what do you", "помощ", "как работа")
    ):
        return ChatIntent.HELP
    return ChatIntent.UNKNOWN


def welcome_text() -> str:
    """Возвращает единое англоязычное приветствие продукта."""
    return (
        "Welcome to Dubai Deal Sniper. I can help you find a car, show the verified "
        "market overview, and share recent Dubai automotive news with sources.\n\n"
        "Choose an action below or describe the car you need in plain English."
    )


def help_text() -> str:
    """Объясняет возможности без требования знать slash-команды."""
    return (
        "Tell me what you need in plain English. For example:\n"
        "• Find a Toyota Land Cruiser under AED 180,000, 2020–2024, GCC specs\n"
        "• Show the Dubai auto market overview\n"
        "• What are the latest Dubai automotive news?\n\n"
        "Prices and deal ratings come only from verified listings and the deterministic "
        "Deal Engine. News never changes a deal score."
    )


def search_prompt_text() -> str:
    """Запрашивает критерии персонального подбора."""
    return (
        "Describe the car you want: make/model, maximum budget in AED, year range, "
        "maximum mileage and GCC specs if required.\n\n"
        "Example: Toyota Camry, budget AED 90,000, 2021–2024, up to 70,000 km, GCC."
    )

"""Типизированная конфигурация приложения из переменных окружения."""

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _integer_set(value: str) -> frozenset[int]:
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Настройки локального MVP и Telegram-интерфейса."""

    telegram_bot_token: str
    telegram_allowed_user_ids: frozenset[int]
    telegram_channel_id: str | None
    database_path: Path
    source_url_template: str
    source_pages: int
    request_timeout_seconds: float
    target_profit_aed: Decimal
    min_roi_percent: Decimal
    min_comparables_count: int
    default_cost_aed: Decimal

    @classmethod
    def from_env(cls) -> "Settings":
        """Создаёт конфигурацию без неявных секретов и mock-режима."""
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_user_ids=_integer_set(os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")),
            telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID") or None,
            database_path=Path(os.getenv("LOCAL_DATABASE_PATH", "data/deal_sniper.db")),
            source_url_template=os.getenv(
                "DUBICARS_URL_TEMPLATE",
                "https://www.dubicars.com/uae/used?page={page}",
            ),
            source_pages=max(1, int(os.getenv("DUBICARS_MAX_PAGES", "3"))),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            target_profit_aed=Decimal(os.getenv("TARGET_PROFIT_AED", "5000")),
            min_roi_percent=Decimal(os.getenv("MIN_ROI_PERCENT", "10")),
            min_comparables_count=max(2, int(os.getenv("MIN_COMPARABLES_COUNT", "3"))),
            default_cost_aed=Decimal(os.getenv("DEFAULT_NON_PURCHASE_COST_AED", "5000")),
        )

    def require_bot_token(self) -> str:
        """Возвращает токен либо останавливает запуск с понятной ошибкой."""
        if not self.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")
        return self.telegram_bot_token

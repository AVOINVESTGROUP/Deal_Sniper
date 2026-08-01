"""Версионированная несекретная конфигурация Control Center R7."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.config import Settings
from src.domain.ids import canonical_hash

SUBSCRIPTION_PERIOD_SECONDS = 30 * 24 * 60 * 60


class RuntimeConfiguration(BaseModel):
    """Immutable revision коммерческих и операционных настроек."""

    model_config = ConfigDict(frozen=True)

    version: str
    state: str = "active"
    pro_price_aed: int = Field(ge=1, le=1_000_000)
    pro_price_stars: int = Field(ge=1, le=10_000)
    pro_subscription_url: str
    subscription_period_seconds: int = SUBSCRIPTION_PERIOD_SECONDS
    target_profit_aed: Decimal = Field(ge=0)
    min_roi_percent: Decimal = Field(ge=0, le=1_000)
    min_comparables_count: int = Field(ge=2, le=100)
    channel_max_posts_per_run: int = Field(ge=1, le=100)
    pro_deals_enabled: bool = True
    pro_news_enabled: bool = False
    pro_news_max_items: int = Field(default=3, ge=1, le=3)
    pro_news_min_interval_hours: int = Field(default=6, ge=1, le=168)
    pro_news_ai_summary_enabled: bool = False
    created_at: datetime
    created_by: str
    previous_version: str | None = None
    telegram_link_name: str = ""

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        if value not in {"active", "archived"}:
            raise ValueError("state должен быть active или archived")
        return value

    @field_validator("pro_subscription_url")
    @classmethod
    def validate_subscription_url(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and not cleaned.startswith(("https://t.me/", "https://telegram.me/")):
            raise ValueError("Разрешена только Telegram subscription URL")
        return cleaned

    @field_validator("subscription_period_seconds")
    @classmethod
    def validate_period(cls, value: int) -> int:
        if value != SUBSCRIPTION_PERIOD_SECONDS:
            raise ValueError("Telegram subscription period должен составлять 30 дней")
        return value

    def public_dict(self) -> dict[str, Any]:
        """Возвращает безопасное представление без раскрытия полного invite link."""
        payload = self.model_dump(mode="json")
        payload["subscription_url_configured"] = bool(self.pro_subscription_url)
        payload["pro_subscription_url"] = mask_subscription_url(self.pro_subscription_url)
        return payload


def configuration_from_settings(settings: Settings) -> RuntimeConfiguration:
    """Строит fail-safe baseline из environment-конфигурации R6."""
    return RuntimeConfiguration(
        version=settings.financial_config_version,
        pro_price_aed=settings.pro_price_aed,
        pro_price_stars=settings.pro_price_stars,
        pro_subscription_url=settings.telegram_pro_subscription_url,
        target_profit_aed=settings.target_profit_aed,
        min_roi_percent=settings.min_roi_percent,
        min_comparables_count=settings.min_comparables_count,
        channel_max_posts_per_run=settings.channel_max_posts_per_run,
        pro_deals_enabled=settings.pro_deals_enabled,
        pro_news_enabled=settings.pro_news_enabled,
        pro_news_max_items=settings.pro_news_max_items,
        pro_news_min_interval_hours=settings.pro_news_min_interval_hours,
        pro_news_ai_summary_enabled=settings.pro_news_ai_summary_enabled,
        created_at=datetime.fromtimestamp(0, UTC),
        created_by="environment",
        telegram_link_name="environment-baseline",
    )


def active_configuration(repository: Any, settings: Settings) -> RuntimeConfiguration:
    """Читает active revision либо безопасно возвращает environment baseline."""
    try:
        stored = repository.get_active_runtime_configuration()
        if stored is not None:
            return RuntimeConfiguration.model_validate(stored)
    except Exception:
        pass
    return configuration_from_settings(settings)


def effective_settings(repository: Any, settings: Settings) -> Settings:
    """Накладывает active revision на immutable environment settings."""
    active = active_configuration(repository, settings)
    financial_values_changed = (
        active.target_profit_aed != settings.target_profit_aed
        or active.min_roi_percent != settings.min_roi_percent
        or active.min_comparables_count != settings.min_comparables_count
    )
    financial_version = settings.financial_config_version
    if financial_values_changed:
        financial_version = "r7-policy-" + canonical_hash(
            "financial-policy/v1",
            {
                "target_profit_aed": active.target_profit_aed,
                "min_roi_percent": active.min_roi_percent,
                "min_comparables_count": active.min_comparables_count,
                "default_cost_aed": settings.default_cost_aed,
                "inspection_cost_aed": settings.inspection_cost_aed,
                "registration_cost_aed": settings.registration_cost_aed,
                "preparation_cost_aed": settings.preparation_cost_aed,
                "repair_expected_aed": settings.repair_expected_aed,
                "holding_cost_per_day_aed": settings.holding_cost_per_day_aed,
                "expected_hold_days": settings.expected_hold_days,
                "annual_capital_rate": settings.annual_capital_rate,
                "selling_rate": settings.selling_rate,
                "risk_rate": settings.risk_rate,
                "liquidity_discount_rate": settings.liquidity_discount_rate,
            },
        )[:16]
    return replace(
        settings,
        telegram_pro_subscription_url=active.pro_subscription_url,
        pro_price_aed=active.pro_price_aed,
        pro_price_stars=active.pro_price_stars,
        target_profit_aed=active.target_profit_aed,
        min_roi_percent=active.min_roi_percent,
        min_comparables_count=active.min_comparables_count,
        channel_max_posts_per_run=active.channel_max_posts_per_run,
        pro_deals_enabled=active.pro_deals_enabled,
        pro_news_enabled=active.pro_news_enabled,
        pro_news_max_items=active.pro_news_max_items,
        pro_news_min_interval_hours=active.pro_news_min_interval_hours,
        pro_news_ai_summary_enabled=active.pro_news_ai_summary_enabled,
        financial_config_version=financial_version,
    )


def mask_subscription_url(value: str) -> str:
    """Маскирует платную invite link для административного ответа."""
    if not value:
        return "not configured"
    if len(value) <= 18:
        return "configured"
    return f"{value[:13]}…{value[-4:]}"

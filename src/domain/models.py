"""Доменные модели, независимые от Telegram и облачной инфраструктуры."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class DecisionAction(StrEnum):
    """Возможное действие по объявлению."""

    CONTACT = "CONTACT"
    WATCH = "WATCH"
    INSPECT = "INSPECT"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SellerType(StrEnum):
    """Тип продавца или ценового ориентира."""

    PRIVATE = "private"
    DEALER = "dealer"
    CERTIFIED = "certified"
    C2B = "c2b"
    UNKNOWN = "unknown"


class ListingSnapshot(BaseModel):
    """Неизменяемый снимок объявления."""

    source: str = Field(min_length=1)
    source_listing_id: str = Field(min_length=1)
    url: HttpUrl
    title: str = Field(min_length=1)
    price_aed: Decimal = Field(gt=0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    trim: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    mileage_km: int | None = Field(default=None, ge=0)
    specification: str | None = None
    vin: str | None = None
    body_type: str | None = None
    transmission: str | None = None
    fuel_type: str | None = None
    location: str | None = None
    seller_type: SellerType = SellerType.UNKNOWN
    description: str = ""
    image_urls: list[HttpUrl] = Field(default_factory=list)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Запрещает неоднозначные даты без часового пояса."""
        if value.tzinfo is None:
            raise ValueError("observed_at должен содержать часовой пояс")
        return value.astimezone(UTC)


class NormalizedVehicle(BaseModel):
    """Канонические признаки объявления для identity resolution и аналогов."""

    listing_id: str
    source: str
    make: str
    model: str
    generation: str | None = None
    trim: str | None = None
    year: int
    mileage_km: int
    mileage_bucket: int
    specification: str | None = None
    vin: str | None = None
    seller_type: SellerType
    asking_price_aed: Decimal = Field(gt=0)
    observed_at: datetime
    comparison_key: str


class VehicleIdentity(BaseModel):
    """Объяснимое объединение публикаций одного предполагаемого автомобиля."""

    vehicle_id: str
    listing_ids: list[str] = Field(min_length=1)
    match_method: str
    confidence: Decimal = Field(ge=0, le=1)
    comparison_key: str
    reasons: list[str] = Field(default_factory=list)


class RawSnapshotMetadata(BaseModel):
    """Проверяемая ссылка на неизменённый ответ внешнего источника."""

    source: str
    source_url: HttpUrl
    storage_uri: str
    checksum_sha256: str
    content_type: str
    size_bytes: int = Field(ge=0)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ComparableVehicle(BaseModel):
    """Нормализованный сопоставимый автомобиль."""

    listing_id: str
    vehicle_id: str | None = None
    source: str | None = None
    price_aed: Decimal = Field(gt=0)
    adjusted_price_aed: Decimal | None = Field(default=None, gt=0)
    adjustments: list[str] = Field(default_factory=list)
    year: int = Field(ge=1950, le=2100)
    mileage_km: int = Field(ge=0)
    seller_type: SellerType
    observed_at: datetime


class MarketEstimate(BaseModel):
    """Рыночный диапазон и доказательная база."""

    low_aed: Decimal
    median_aed: Decimal
    high_aed: Decimal
    comparable_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    coverage_score: Decimal = Field(ge=0, le=1)


class CostEstimate(BaseModel):
    """Непокупные расходы на одну сделку."""

    inspection_aed: Decimal = Decimal("0")
    repair_aed: Decimal = Decimal("0")
    preparation_aed: Decimal = Decimal("0")
    holding_aed: Decimal = Decimal("0")
    capital_aed: Decimal = Decimal("0")
    selling_aed: Decimal = Decimal("0")
    risk_reserve_aed: Decimal = Decimal("0")

    @property
    def total_aed(self) -> Decimal:
        """Возвращает сумму всех расходов."""
        return sum(
            (
                self.inspection_aed,
                self.repair_aed,
                self.preparation_aed,
                self.holding_aed,
                self.capital_aed,
                self.selling_aed,
                self.risk_reserve_aed,
            ),
            Decimal("0"),
        )


class RiskAssessment(BaseModel):
    """Результат проверки рисков."""

    stop_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_quality_score: Decimal = Field(default=Decimal("1"), ge=0, le=1)


class DealDecision(BaseModel):
    """Полностью объяснимое финансовое решение."""

    action: DecisionAction
    asking_price_aed: Decimal
    market: MarketEstimate | None
    costs: CostEstimate
    risks: RiskAssessment
    max_purchase_price_aed: Decimal | None
    expected_profit_aed: Decimal | None
    roi_percent: Decimal | None
    confidence: Decimal = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    engine_version: str = "2.2.1"


class Outcome(BaseModel):
    """Фактический результат сделки для пилота и последующей калибровки."""

    listing_id: str
    decision_content_hash: str
    status: str
    purchase_price_aed: Decimal | None = None
    actual_cost_aed: Decimal | None = None
    sale_price_aed: Decimal | None = None
    hold_days: int | None = Field(default=None, ge=0)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserSettings(BaseModel):
    """Персональные фильтры Telegram-пользователя."""

    user_id: int
    max_budget_aed: Decimal | None = Field(default=None, gt=0)
    min_profit_aed: Decimal = Field(default=Decimal("5000"), ge=0)
    min_roi_percent: Decimal = Field(default=Decimal("10"), ge=0)
    makes: list[str] = Field(default_factory=list)
    language_code: str = "en"


class UserAction(BaseModel):
    """Состояние кандидата в пользовательской воронке."""

    user_id: int
    listing_id: str
    action: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

"""Доменные модели, независимые от Telegram и облачной инфраструктуры."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator

MIN_VALID_LISTING_PRICE_AED = Decimal("5000")


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


class VerificationStatus(StrEnum):
    """Семантический результат проверки detail page."""

    PENDING = "pending"
    VERIFIED = "verified"
    TEMPORARY_ERROR = "temporary_error"
    PERMANENT_INVALID = "permanent_invalid"


class FreshnessStatus(StrEnum):
    """Операционное состояние TTL неизменяемого evidence."""

    ACTIVE = "active"
    EXPIRED = "expired"


class ListingLifecycle(StrEnum):
    """Жизненный цикл объявления."""

    ACTIVE = "active"
    CHANGED = "changed"
    STALE = "stale"
    REMOVED = "removed"
    QUARANTINED = "quarantined"


class SourceConfiguration(BaseModel):
    """Проверенная конфигурация динамического источника объявлений."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,39}$")
    kind: str = Field(default="json_feed", pattern=r"^json_feed$")
    url: HttpUrl
    enabled: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_count: int = Field(default=0, ge=0)


class OutboxState(StrEnum):
    """Состояние внешней доставки без ложного exactly-once."""

    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProcessingState(StrEnum):
    """Состояние идемпотентной обработки Telegram update."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ClusterStatus(StrEnum):
    """Состояние identity cluster."""

    CONFIRMED = "confirmed"
    REVIEW = "review"
    SPLIT = "split"
    MERGED = "merged"


class ListingSnapshot(BaseModel):
    """Неизменяемый снимок объявления."""

    source: str = Field(min_length=1)
    source_listing_id: str = Field(min_length=1)
    url: HttpUrl
    title: str = Field(min_length=1)
    price_aed: Decimal = Field(gt=0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_observed_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ingested_at: datetime | None = None
    version_sequence: int | None = Field(default=None, ge=0)
    lifecycle: ListingLifecycle = ListingLifecycle.ACTIVE
    schema_version: str = "listing-snapshot/v2"
    correlation_id: str | None = None
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

    @field_validator("observed_at", "source_observed_at", "fetched_at", "ingested_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Запрещает неоднозначные даты без часового пояса."""
        if value is None:
            return None
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
    vehicle_id: str | None = None
    lifecycle: ListingLifecycle = ListingLifecycle.ACTIVE
    verification_status: VerificationStatus = VerificationStatus.PENDING
    evidence_revision_id: str | None = None
    valid_until: datetime | None = None
    freshness_status: FreshnessStatus = FreshnessStatus.EXPIRED
    schema_version: str = "normalized-vehicle/v2"


class VehicleIdentity(BaseModel):
    """Объяснимое объединение публикаций одного предполагаемого автомобиля."""

    vehicle_id: str
    listing_ids: list[str] = Field(min_length=1)
    match_method: str
    confidence: Decimal = Field(ge=0, le=1)
    comparison_key: str
    reasons: list[str] = Field(default_factory=list)
    identity_version: str = "vehicle-identity/v3"
    cluster_status: ClusterStatus = ClusterStatus.CONFIRMED
    evidence: list[dict[str, str]] = Field(default_factory=list)
    merge_events: list[dict[str, str]] = Field(default_factory=list)
    split_events: list[dict[str, str]] = Field(default_factory=list)


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
    evidence_revision_id: str | None = None
    accepted: bool = True
    reason: str = "accepted"
    adjustment_version: str = "comparable-adjustments/v1"


class MarketEstimate(BaseModel):
    """Рыночный диапазон и доказательная база."""

    low_aed: Decimal
    median_aed: Decimal
    high_aed: Decimal
    comparable_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    coverage_score: Decimal = Field(ge=0, le=1)
    market_fingerprint: str | None = None
    adjustment_version: str = "comparable-adjustments/v1"


class CostEstimate(BaseModel):
    """Непокупные расходы на одну сделку."""

    inspection_aed: Decimal = Decimal("0")
    registration_aed: Decimal = Decimal("0")
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
                self.registration_aed,
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
    engine_version: str = "3.0.0"
    decision_id: str | None = None
    decision_subject_id: str | None = None
    vehicle_id: str | None = None
    content_hash: str | None = None
    financial_config_version: str = "provisional-2026-07-v1"
    verification_version: str | None = None
    market_fingerprint: str | None = None
    superseded_by: str | None = None
    is_current: bool = True
    schema_version: str = "deal-decision/v2"


class Outcome(BaseModel):
    """Фактический результат сделки для пилота и последующей калибровки."""

    user_id: int
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
    models: list[str] = Field(default_factory=list)
    min_year: int | None = Field(default=None, ge=1950, le=2100)
    max_year: int | None = Field(default=None, ge=1950, le=2100)
    max_mileage_km: int | None = Field(default=None, ge=0)
    specifications: list[str] = Field(default_factory=list)
    body_types: list[str] = Field(default_factory=list)
    tariff: str = "free"
    referred_by_user_id: int | None = None


class UserAction(BaseModel):
    """Состояние кандидата в пользовательской воронке."""

    user_id: int
    listing_id: str
    action: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationEvidence(BaseModel):
    """Immutable price evidence с отдельно обновляемой freshness."""

    verification_key: str
    evidence_revision_id: str
    listing_id: str
    content_hash: str
    source: str
    status: VerificationStatus
    freshness_status: FreshnessStatus
    verified_price_aed: Decimal | None = None
    currency: str | None = None
    checksum_sha256: str | None = None
    extractor_version: str
    rejection_reason: str | None = None
    source_response_uri: str | None = None
    evidence_created_at: datetime
    last_checked_at: datetime
    valid_until: datetime
    attempt_count: int = Field(default=1, ge=1)
    latency_ms: int | None = Field(default=None, ge=0)
    schema_version: str = "verification-evidence/v2"


class OutboxRecord(BaseModel):
    """Проверяемая запись внешней доставки."""

    delivery_id: str
    decision_id: str
    recipient: str
    template_version: str
    format: str
    payload: dict[str, object] = Field(default_factory=dict)
    state: OutboxState = OutboxState.PENDING
    attempt_id: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error: str | None = None
    telegram_message_id: str | None = None
    provider_message_id: str | None = None
    retry_once_used: bool = False
    audit_events: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "outbox/v2"


class SavedSearch(BaseModel):
    """Owner-scoped подтверждённый поисковый запрос."""

    search_id: str
    user_id: int
    query_text: str
    filters: UserSettings
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PublicationEvent(BaseModel):
    """Единый факт публикации для Telegram, WhatsApp и TMA."""

    publication_event_id: str
    decision_id: str
    vehicle_id: str
    event_type: str
    parent_publication_event_id: str | None = None
    recipient: str | None = None
    pro_cta_variant_id: str | None = None
    pro_cta_text: str | None = None
    pro_cta_button_label: str | None = None
    pro_cta_target: str | None = None
    pro_cta_fingerprint: str | None = None
    pro_cta_template_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    template_version: str = "publication/v3"


class TelegramUpdateRecord(BaseModel):
    """Lease-состояние обработки входящего Telegram update."""

    update_id: int
    state: ProcessingState
    operation_id: str
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

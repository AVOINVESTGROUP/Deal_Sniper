"""Отбор и детерминированные поправки сопоставимых автомобилей."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from src.domain.models import (
    MIN_VALID_LISTING_PRICE_AED,
    ComparableVehicle,
    NormalizedVehicle,
    SellerType,
)

MAX_AGE = timedelta(days=14)
MAX_YEAR_GAP = 2
MAX_MILEAGE_GAP_KM = 50_000


def select_comparables(
    target: NormalizedVehicle,
    vehicles: list[NormalizedVehicle],
    listing_to_vehicle: dict[str, str],
    *,
    now: datetime | None = None,
    min_comparables: int = 1,
) -> list[ComparableVehicle]:
    """Выбирает минимально достаточную доказуемую когорту из трёх уровней."""
    reference_time = now or datetime.now(UTC)
    target_vehicle_id = listing_to_vehicle.get(target.listing_id)
    selected_by_tier: dict[int, dict[str, ComparableVehicle]] = {1: {}, 2: {}, 3: {}}
    for candidate in vehicles:
        if candidate.listing_id == target.listing_id:
            continue
        if candidate.asking_price_aed < MIN_VALID_LISTING_PRICE_AED:
            continue
        candidate_vehicle_id = listing_to_vehicle.get(candidate.listing_id, candidate.listing_id)
        if target_vehicle_id and candidate_vehicle_id == target_vehicle_id:
            continue
        if candidate.make != target.make or candidate.model != target.model:
            continue
        if abs(candidate.year - target.year) > MAX_YEAR_GAP:
            continue
        if reference_time - candidate.observed_at > MAX_AGE:
            continue
        if candidate.seller_type == SellerType.C2B:
            continue
        generation_compatible = not (
            target.generation
            and candidate.generation
            and target.generation != candidate.generation
        )
        exact_specification = bool(
            target.specification
            and candidate.specification
            and target.specification == candidate.specification
        )
        exact_trim = bool(target.trim and candidate.trim and target.trim == candidate.trim)
        mileage_close = abs(candidate.mileage_km - target.mileage_km) <= MAX_MILEAGE_GAP_KM
        if generation_compatible and exact_specification and exact_trim and mileage_close:
            tier = 1
            reason = "точные make/model/generation/specification/trim"
        elif generation_compatible:
            tier = 2
            reason = "make/model/generation с детерминированными поправками"
        else:
            tier = 3
            reason = "make/model и год ±2; широкая когорта"
        comparable = _adjust_comparable(
            target,
            candidate,
            candidate_vehicle_id,
            cohort_tier=tier,
            reason=reason,
        )
        previous = selected_by_tier[tier].get(candidate_vehicle_id)
        if previous is None or candidate.observed_at > previous.observed_at:
            selected_by_tier[tier][candidate_vehicle_id] = comparable

    accumulated: dict[str, ComparableVehicle] = {}
    for tier in (1, 2, 3):
        for vehicle_id, comparable in selected_by_tier[tier].items():
            accumulated.setdefault(vehicle_id, comparable)
        if len(accumulated) >= min_comparables:
            break
    return list(accumulated.values())


def _adjust_comparable(
    target: NormalizedVehicle,
    candidate: NormalizedVehicle,
    vehicle_id: str,
    *,
    cohort_tier: int,
    reason: str,
) -> ComparableVehicle:
    factor = Decimal("1")
    adjustments: list[str] = []

    year_gap = candidate.year - target.year
    if year_gap:
        year_adjustment = Decimal(year_gap) * Decimal("0.03")
        factor -= year_adjustment
        adjustments.append(f"Поправка за год: {-year_adjustment * 100:+.1f}%")

    mileage_gap = target.mileage_km - candidate.mileage_km
    mileage_adjustment = Decimal(mileage_gap) / Decimal("10000") * Decimal("0.01")
    if mileage_adjustment:
        factor -= mileage_adjustment
        adjustments.append(f"Поправка за пробег: {-mileage_adjustment * 100:+.1f}%")

    seller_adjustment = {
        SellerType.CERTIFIED: Decimal("0.05"),
        SellerType.DEALER: Decimal("0.03"),
        SellerType.PRIVATE: Decimal("0"),
        SellerType.UNKNOWN: Decimal("0.02"),
    }.get(candidate.seller_type, Decimal("0"))
    if seller_adjustment:
        factor -= seller_adjustment
        adjustments.append(f"Поправка типа продавца: {-seller_adjustment * 100:+.1f}%")

    if target.specification != candidate.specification:
        specification_adjustment = Decimal("0.03")
        factor -= specification_adjustment
        adjustments.append("Поправка за неподтверждённое совпадение спецификации: -3.0%")
    if target.trim != candidate.trim:
        trim_adjustment = Decimal("0.02")
        factor -= trim_adjustment
        adjustments.append("Поправка за неподтверждённое совпадение комплектации: -2.0%")

    factor = max(Decimal("0.7"), min(Decimal("1.3"), factor))
    adjusted = (candidate.asking_price_aed * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return ComparableVehicle(
        listing_id=candidate.listing_id,
        vehicle_id=vehicle_id,
        source=candidate.source,
        price_aed=candidate.asking_price_aed,
        adjusted_price_aed=adjusted,
        adjustments=adjustments,
        year=candidate.year,
        mileage_km=candidate.mileage_km,
        seller_type=candidate.seller_type,
        observed_at=candidate.observed_at,
        evidence_revision_id=candidate.evidence_revision_id,
        reason=reason,
        cohort_tier=cohort_tier,
        adjustment_version="comparable-adjustments/v3",
    )

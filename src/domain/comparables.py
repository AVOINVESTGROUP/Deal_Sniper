"""Отбор и детерминированные поправки сопоставимых автомобилей."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from src.domain.models import ComparableVehicle, NormalizedVehicle, SellerType

MAX_AGE = timedelta(days=14)
MAX_YEAR_GAP = 2
MAX_MILEAGE_GAP_KM = 50_000


def select_comparables(
    target: NormalizedVehicle,
    vehicles: list[NormalizedVehicle],
    listing_to_vehicle: dict[str, str],
    *,
    now: datetime | None = None,
) -> list[ComparableVehicle]:
    """Выбирает аналоги по ключевым признакам и исключает межсайтовые дубли."""
    reference_time = now or datetime.now(UTC)
    target_vehicle_id = listing_to_vehicle.get(target.listing_id)
    selected_by_vehicle: dict[str, ComparableVehicle] = {}
    for candidate in vehicles:
        if candidate.listing_id == target.listing_id:
            continue
        candidate_vehicle_id = listing_to_vehicle.get(candidate.listing_id, candidate.listing_id)
        if target_vehicle_id and candidate_vehicle_id == target_vehicle_id:
            continue
        if candidate.make != target.make or candidate.model != target.model:
            continue
        if abs(candidate.year - target.year) > MAX_YEAR_GAP:
            continue
        if abs(candidate.mileage_km - target.mileage_km) > MAX_MILEAGE_GAP_KM:
            continue
        if reference_time - candidate.observed_at > MAX_AGE:
            continue
        if target.generation and candidate.generation and target.generation != candidate.generation:
            continue
        if target.specification and candidate.specification:
            if target.specification != candidate.specification:
                continue
        if target.trim and candidate.trim and target.trim != candidate.trim:
            continue
        if candidate.seller_type == SellerType.C2B:
            continue
        comparable = _adjust_comparable(target, candidate, candidate_vehicle_id)
        previous = selected_by_vehicle.get(candidate_vehicle_id)
        if previous is None or candidate.observed_at > previous.observed_at:
            selected_by_vehicle[candidate_vehicle_id] = comparable
    return list(selected_by_vehicle.values())


def _adjust_comparable(
    target: NormalizedVehicle,
    candidate: NormalizedVehicle,
    vehicle_id: str,
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
    )

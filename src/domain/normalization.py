"""Детерминированная нормализация и объединение автомобилей между источниками."""

import re
from collections import defaultdict
from decimal import Decimal

from src.domain.ids import canonical_hash
from src.domain.models import (
    MIN_VALID_LISTING_PRICE_AED,
    ListingSnapshot,
    NormalizedVehicle,
    VehicleIdentity,
)

SPACE_PATTERN = re.compile(r"[^a-z0-9]+")
MAKE_ALIASES = {
    "mercedes benz": "mercedes-benz",
    "mercedesbenz": "mercedes-benz",
    "land rover": "land-rover",
    "rolls royce": "rolls-royce",
    "alfa romeo": "alfa-romeo",
}


def canonical_text(value: str | None) -> str | None:
    """Приводит свободный текст к устойчивому ключу без выдумывания значений."""
    if value is None:
        return None
    normalized = SPACE_PATTERN.sub(" ", value.casefold()).strip()
    return normalized or None


def valid_vin(value: str | None) -> str | None:
    """Возвращает канонический VIN либо None для заглушки/невалидного значения."""
    if value is None:
        return None
    normalized = value.strip().upper()
    if len(normalized) != 17 or not normalized.isalnum():
        return None
    if any(character in "IOQ" for character in normalized):
        return None
    if len(set(normalized)) < 5 or normalized in {"0" * 17, "1" * 17, "X" * 17}:
        return None
    return normalized


def normalize_listing(listing: ListingSnapshot) -> NormalizedVehicle | None:
    """Возвращает канонический автомобиль только при наличии обязательных признаков."""
    if listing.price_aed < MIN_VALID_LISTING_PRICE_AED:
        return None
    if not listing.make or not listing.model or listing.year is None or listing.mileage_km is None:
        return None
    make_raw = canonical_text(listing.make)
    model = canonical_text(listing.model)
    if make_raw is None or model is None:
        return None
    make = MAKE_ALIASES.get(make_raw, make_raw.replace(" ", "-"))
    generation = canonical_text(listing.generation)
    trim = canonical_text(listing.trim)
    specification = canonical_text(listing.specification)
    vin = valid_vin(listing.vin)
    mileage_bucket = (listing.mileage_km // 10_000) * 10_000
    comparison_parts = [make, model, str(listing.year)]
    if generation:
        comparison_parts.append(generation)
    if specification:
        comparison_parts.append(specification)
    return NormalizedVehicle(
        listing_id=f"{listing.source}:{listing.source_listing_id}",
        source=listing.source,
        make=make,
        model=model,
        generation=generation,
        trim=trim,
        year=listing.year,
        mileage_km=listing.mileage_km,
        mileage_bucket=mileage_bucket,
        specification=specification,
        vin=vin,
        seller_type=listing.seller_type,
        asking_price_aed=listing.price_aed,
        observed_at=listing.observed_at,
        comparison_key=canonical_hash("vehicle-comparison-key/v1", {"parts": comparison_parts}),
    )


def resolve_vehicle_identities(
    vehicles: list[NormalizedVehicle],
) -> tuple[list[VehicleIdentity], dict[str, str]]:
    """Автоматически объединяет только объявления с одинаковым валидным VIN.

    Без VIN похожие объявления остаются отдельными identity: неясное fuzzy-совпадение
    нельзя превращать в транзитивный production merge без ручного подтверждения.
    """
    groups: list[list[NormalizedVehicle]] = []
    assigned: set[str] = set()
    by_vin: dict[str, list[NormalizedVehicle]] = defaultdict(list)
    for vehicle in vehicles:
        if vehicle.vin:
            by_vin[vehicle.vin].append(vehicle)

    for vin_group in by_vin.values():
        groups.append(vin_group)
        assigned.update(item.listing_id for item in vin_group)

    for vehicle in vehicles:
        if vehicle.listing_id not in assigned:
            groups.append([vehicle])
            assigned.add(vehicle.listing_id)

    identities: list[VehicleIdentity] = []
    listing_to_vehicle: dict[str, str] = {}
    for group in groups:
        listing_ids = sorted(item.listing_id for item in group)
        has_shared_vin = bool(group[0].vin) and all(item.vin == group[0].vin for item in group)
        method = "vin" if has_shared_vin else "single"
        confidence = Decimal("1") if has_shared_vin else Decimal("0.5")
        vehicle_id = canonical_hash(
            "vehicle-identity/v3",
            {
                "vin": group[0].vin if has_shared_vin else None,
                "listing_id": None if has_shared_vin else listing_ids[0],
                "method": method,
            },
        )
        reasons = (
            ["Совпадает VIN"]
            if has_shared_vin
            else ["Без валидного VIN автоматическое межсайтовое объединение запрещено"]
        )
        identity = VehicleIdentity(
            vehicle_id=vehicle_id,
            listing_ids=listing_ids,
            match_method=method,
            confidence=confidence,
            comparison_key=group[0].comparison_key,
            reasons=reasons,
            evidence=[
                {
                    "listing_id": item.listing_id,
                    "source": item.source,
                    "evidence_revision_id": item.evidence_revision_id or "missing",
                }
                for item in group
            ],
        )
        identities.append(identity)
        for listing_id in listing_ids:
            listing_to_vehicle[listing_id] = vehicle_id
    return identities, listing_to_vehicle

"""Детерминированная нормализация и объединение автомобилей между источниками."""

import hashlib
import re
from collections import defaultdict
from decimal import Decimal

from src.domain.models import ListingSnapshot, NormalizedVehicle, VehicleIdentity

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


def normalize_listing(listing: ListingSnapshot) -> NormalizedVehicle | None:
    """Возвращает канонический автомобиль только при наличии обязательных признаков."""
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
    vin = canonical_text(listing.vin)
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
        comparison_key="|".join(comparison_parts),
    )


def resolve_vehicle_identities(
    vehicles: list[NormalizedVehicle],
) -> tuple[list[VehicleIdentity], dict[str, str]]:
    """Объединяет только сильные межсайтовые совпадения и объясняет использованные признаки."""
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
        if vehicle.listing_id in assigned:
            continue
        matching_group: list[NormalizedVehicle] | None = None
        for group in groups:
            if any(_strong_attribute_match(vehicle, candidate) for candidate in group):
                matching_group = group
                break
        if matching_group is None:
            matching_group = [vehicle]
            groups.append(matching_group)
        else:
            matching_group.append(vehicle)
        assigned.add(vehicle.listing_id)

    identities: list[VehicleIdentity] = []
    listing_to_vehicle: dict[str, str] = {}
    for group in groups:
        listing_ids = sorted(item.listing_id for item in group)
        has_shared_vin = bool(group[0].vin) and all(item.vin == group[0].vin for item in group)
        method = "vin" if has_shared_vin else "strong_attributes" if len(group) > 1 else "single"
        confidence = (
            Decimal("1")
            if has_shared_vin
            else Decimal("0.9")
            if len(group) > 1
            else Decimal("0.5")
        )
        vehicle_id = hashlib.sha256("|".join(listing_ids).encode()).hexdigest()
        reasons = (
            ["Совпадает VIN"]
            if has_shared_vin
            else ["Совпадают марка, модель, год, пробег, цена и доступные спецификации"]
            if len(group) > 1
            else ["Межсайтовое совпадение не найдено"]
        )
        identity = VehicleIdentity(
            vehicle_id=vehicle_id,
            listing_ids=listing_ids,
            match_method=method,
            confidence=confidence,
            comparison_key=group[0].comparison_key,
            reasons=reasons,
        )
        identities.append(identity)
        for listing_id in listing_ids:
            listing_to_vehicle[listing_id] = vehicle_id
    return identities, listing_to_vehicle


def _strong_attribute_match(left: NormalizedVehicle, right: NormalizedVehicle) -> bool:
    if left.source == right.source:
        return False
    if (left.make, left.model, left.year) != (right.make, right.model, right.year):
        return False
    if abs(left.mileage_km - right.mileage_km) > 250:
        return False
    if _relative_price_gap(left.asking_price_aed, right.asking_price_aed) > Decimal("0.03"):
        return False
    if left.trim and right.trim and left.trim != right.trim:
        return False
    if left.specification and right.specification and left.specification != right.specification:
        return False
    return True


def _relative_price_gap(left: Decimal, right: Decimal) -> Decimal:
    return abs(left - right) / max(left, right)

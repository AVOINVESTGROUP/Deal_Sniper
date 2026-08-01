"""Проверки канонизации, межсайтового объединения и отбора аналогов."""

from datetime import UTC, datetime
from decimal import Decimal

from src.domain.comparables import select_comparables
from src.domain.models import ListingSnapshot, SellerType
from src.domain.normalization import normalize_listing, resolve_vehicle_identities


def snapshot(
    source: str,
    source_id: str,
    *,
    year: int = 2022,
    mileage: int = 40_000,
    price: str = "80000",
    trim: str = "SE",
    vin: str | None = None,
) -> ListingSnapshot:
    return ListingSnapshot(
        source=source,
        source_listing_id=source_id,
        url=f"https://example.com/{source}/{source_id}",
        title="Toyota Camry SE",
        price_aed=Decimal(price),
        observed_at=datetime.now(UTC),
        make="Toyota",
        model="Camry",
        trim=trim,
        year=year,
        mileage_km=mileage,
        specification="GCC",
        seller_type=SellerType.DEALER,
        vin=vin,
    )


def test_cross_source_identity_and_comparable_deduplication() -> None:
    vin = "JTDKN3DU0A0123456"
    target = normalize_listing(snapshot("cars24", "1", vin=vin))
    duplicate = normalize_listing(
        snapshot("carswitch", "2", mileage=40_100, price="81000", vin=vin)
    )
    peer = normalize_listing(snapshot("dubicars", "3", mileage=55_000, price="85000"))
    assert target is not None
    assert duplicate is not None
    assert peer is not None

    identities, mapping = resolve_vehicle_identities([target, duplicate, peer])

    assert len(identities) == 2
    assert mapping[target.listing_id] == mapping[duplicate.listing_id]
    comparables = select_comparables(target, [target, duplicate, peer], mapping)
    assert [item.listing_id for item in comparables] == [peer.listing_id]
    assert comparables[0].adjusted_price_aed is not None
    assert comparables[0].adjustments


def test_invalid_vin_does_not_trigger_cross_source_auto_merge() -> None:
    first = normalize_listing(snapshot("cars24", "1", vin="N/A"))
    second = normalize_listing(snapshot("carswitch", "2", vin="00000000000000000"))
    assert first is not None and second is not None
    identities, mapping = resolve_vehicle_identities([first, second])
    assert len(identities) == 2
    assert mapping[first.listing_id] != mapping[second.listing_id]


def test_comparable_selection_uses_tier_two_for_different_trim() -> None:
    target = normalize_listing(snapshot("cars24", "1"))
    old = normalize_listing(snapshot("carswitch", "2", year=2018))
    wrong_trim = normalize_listing(snapshot("dubicars", "3", trim="Sport"))
    assert target is not None
    assert old is not None
    assert wrong_trim is not None
    identities, mapping = resolve_vehicle_identities([target, old, wrong_trim])
    assert identities
    comparables = select_comparables(target, [target, old, wrong_trim], mapping)
    assert len(comparables) == 1
    assert comparables[0].listing_id == wrong_trim.listing_id
    assert comparables[0].cohort_tier == 2
    assert any("комплектации" in item for item in comparables[0].adjustments)

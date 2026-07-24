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
    )


def test_cross_source_identity_and_comparable_deduplication() -> None:
    target = normalize_listing(snapshot("cars24", "1"))
    duplicate = normalize_listing(
        snapshot("carswitch", "2", mileage=40_100, price="81000")
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


def test_comparable_selection_rejects_different_year_and_trim() -> None:
    target = normalize_listing(snapshot("cars24", "1"))
    old = normalize_listing(snapshot("carswitch", "2", year=2018))
    wrong_trim = normalize_listing(snapshot("dubicars", "3", trim="Sport"))
    assert target is not None
    assert old is not None
    assert wrong_trim is not None
    identities, mapping = resolve_vehicle_identities([target, old, wrong_trim])
    assert identities
    assert select_comparables(target, [target, old, wrong_trim], mapping) == []

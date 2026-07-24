"""Контрактные проверки источника и истории объявлений."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from src.domain.models import ListingSnapshot
from src.domain.normalization import normalize_listing, resolve_vehicle_identities
from src.sources.cars24 import parse_cars24_page
from src.sources.carswitch import parse_carswitch_page
from src.sources.dubicars import parse_search_page
from src.storage import LocalRepository

SEARCH_HTML = """
<html><head><script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [{
    "@type": "ItemList",
    "itemListElement": [{
      "@type": "ListItem",
      "position": 1,
      "item": {
        "@type": "Car",
        "name": "Toyota Camry",
        "url": "https://www.dubicars.com/2022-toyota-camry-example-123456.html",
        "image": "https://example.com/camry.jpg",
        "brand": {"@id": "https://www.dubicars.com/new-cars/toyota#brand"},
        "model": {"@id": "https://www.dubicars.com/new-cars/toyota/camry#model"},
        "vehicleModelDate": "2022",
        "mileageFromOdometer": {"value": 42000, "unitCode": "KMT"},
        "offers": {"price": "79000", "priceCurrency": "AED"}
      }
    }]
  }]
}
</script></head></html>
"""

CARSWITCH_HTML = """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "itemListElement": [{
    "@type": "ItemPage",
    "mainEntity": {
      "name": "2016 Porsche Macan S",
      "url": "https://carswitch.com/dubai/used-car/porsche/macan/2016/841364",
      "image": ["https://example.com/car.jpg"],
      "description": "Certified car",
      "brand": {"name": "Porsche"},
      "model": "Macan",
      "vehicleModelDate": "2016",
      "mileageFromOdometer": {"value": 254400},
      "offers": {"price": "38150", "priceCurrency": "AED"}
    }
  }]
}
</script>
"""

CARS24_HTML = """
<script>
window.__PRELOADED_STATE__ = {
  "carListing": {
    "content": [{
      "appointmentId": "9714840800",
      "make": "MITSUBISHI",
      "model": "ASX",
      "year": "2021",
      "variant": "GLX LOWLINE",
      "listingActive": true,
      "booked": false,
      "price": 33999,
      "odometerReading": 78171,
      "city": "Dubai",
      "shareUrl": "https://c24ae.live/example",
      "mainImage": {"path": "cars/9714840800/front.jpg"}
    }]
  }
};
</script>
"""


def listing(price: str) -> ListingSnapshot:
    """Создаёт версию одного объявления."""
    return ListingSnapshot(
        source="test",
        source_listing_id="42",
        url="https://example.com/car/42",
        title="Toyota Camry",
        price_aed=Decimal(price),
        observed_at=datetime.now(UTC),
        make="Toyota",
        model="Camry",
        year=2022,
        mileage_km=42_000,
    )


def test_dubicars_json_ld_parser() -> None:
    results = parse_search_page(SEARCH_HTML)
    assert len(results) == 1
    assert results[0].source_listing_id == "123456"
    assert results[0].make == "Toyota"
    assert results[0].model == "Camry"
    assert results[0].price_aed == Decimal("79000")


def test_carswitch_json_ld_parser() -> None:
    results = parse_carswitch_page(CARSWITCH_HTML)
    assert len(results) == 1
    assert results[0].source_listing_id == "841364"
    assert results[0].make == "Porsche"
    assert results[0].model == "Macan"
    assert results[0].price_aed == Decimal("38150")


def test_cars24_preloaded_state_parser() -> None:
    results = parse_cars24_page(CARS24_HTML)
    assert len(results) == 1
    assert results[0].source_listing_id == "9714840800"
    assert results[0].make == "Mitsubishi"
    assert results[0].model == "Asx"
    assert results[0].price_aed == Decimal("33999")
    assert results[0].mileage_km == 78_171


def test_repository_detects_duplicate_and_price_change(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "deal_sniper.db")
    first = repository.save_snapshot(listing("79000"))
    duplicate = repository.save_snapshot(listing("79000"))
    changed = repository.save_snapshot(listing("75000"))

    assert first[:2] == (True, False)
    assert duplicate[:2] == (False, False)
    assert changed[:2] == (False, True)
    assert repository.count_snapshots() == 2

    assert not repository.notification_sent("channel", "test:42", changed[2])
    repository.mark_notification_sent("channel", "test:42", changed[2])
    assert repository.notification_sent("channel", "test:42", changed[2])

    assert repository.source_enabled("cars24")
    repository.set_source_enabled("cars24", False)
    assert not repository.source_enabled("cars24")
    repository.set_source_enabled("cars24", True)
    assert repository.source_enabled("cars24")

    assert repository.claim_telegram_update(12345)
    assert not repository.claim_telegram_update(12345)
    assert repository.claim_telegram_update(12346)

    normalized = normalize_listing(listing("75000"))
    assert normalized is not None
    repository.save_normalized_vehicle(normalized)
    identities, _mapping = resolve_vehicle_identities([normalized])
    repository.save_vehicle_identity(identities[0])

"""Контрактные проверки источника и истории объявлений."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    RiskAssessment,
)
from src.domain.normalization import normalize_listing, resolve_vehicle_identities
from src.raw_storage import _upload_once
from src.sources.cars24 import parse_cars24_page
from src.sources.carswitch import parse_carswitch_page
from src.sources.dubicars import parse_search_page
from src.sources.opensooq import parse_opensooq_page
from src.storage import LocalRepository
from src.verification import extract_detail_prices


class FakeGcsBlob:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upload_from_string(self, payload: bytes, **kwargs: object) -> None:
        self.calls.append({"payload": payload, **kwargs})


def test_gcs_raw_upload_is_atomic_without_preliminary_read() -> None:
    blob = FakeGcsBlob()

    _upload_once(blob, b"raw", "text/html")

    assert blob.calls == [
        {
            "payload": b"raw",
            "content_type": "text/html",
            "if_generation_match": 0,
        }
    ]

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

OPENSOOQ_HTML = """
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {"pageProps": {"serpApiResponse": {"listings": {"items": [{
    "id": 284463144,
    "is_active": true,
    "title": "2008 Mercedes Benz S-Class S 550",
    "price_amount": "20,000 AED",
    "price_currency_iso": "AED",
    "city_label": "Al Ain",
    "post_url": "/search/284463144",
    "image_uri": "e7/aa/example.jpg",
    "kilometers_Cars_value_i": "150000",
    "user_target_type": "free",
    "masked_description": "Used car",
    "cps": ["Used", "Mercedes Benz", "S-Class", "S 550", "2,008", "150,000 km", "Sedan"],
    "starCps": [{"label": "Japanese Specs"}]
  }]}}}}}
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


def test_dubicars_rejects_placeholder_price() -> None:
    html = SEARCH_HTML.replace('"79000"', '"272"').replace('"AED"', '"USD"')
    assert parse_search_page(html) == []


def test_detail_price_requires_positive_aed_offer() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"Car","offers":{"price":"0","priceCurrency":"AED"}}
    </script>
    <script type="application/ld+json">
    {"@type":"Vehicle","offers":[{"price":"95000","priceCurrency":"AED"}]}
    </script>
    """
    assert extract_detail_prices(html) == [Decimal("95000")]


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


def test_opensooq_next_data_parser() -> None:
    results = parse_opensooq_page(OPENSOOQ_HTML)
    assert len(results) == 1
    assert results[0].source_listing_id == "284463144"
    assert results[0].make == "Mercedes Benz"
    assert results[0].model == "S-Class"
    assert results[0].trim == "S 550"
    assert results[0].year == 2008
    assert results[0].mileage_km == 150_000
    assert results[0].price_aed == Decimal("20000")
    assert results[0].specification == "Japanese Specs"


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


def test_out_of_order_snapshot_never_replaces_newer_current(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "out-of-order.db")
    newer = listing("75000").model_copy(update={"version_sequence": 2})
    older = listing("79000").model_copy(update={"version_sequence": 1})

    newer_hash = repository.save_snapshot(newer)[2]
    older_hash = repository.save_snapshot(older)[2]

    current = repository.latest_snapshot("test:42")
    assert current is not None
    assert current.price_aed == Decimal("75000")
    assert current.version_sequence == 2
    assert repository.get_snapshot("test:42", newer_hash) is not None
    assert repository.get_snapshot("test:42", older_hash) is not None
    assert repository.get_snapshot("test:42", "missing") is None


def test_latest_decisions_skips_non_candidates_before_limit(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "deal_sniper.db")
    candidate = listing("70000")
    candidate_result = repository.save_snapshot(candidate)
    repository.save_decision(
        "test:42",
        candidate_result[2],
        DealDecision(
            action=DecisionAction.CONTACT,
            asking_price_aed=Decimal("70000"),
            market=None,
            costs=CostEstimate(),
            risks=RiskAssessment(),
            max_purchase_price_aed=Decimal("75000"),
            expected_profit_aed=Decimal("8000"),
            roi_percent=Decimal("11"),
            confidence=Decimal("0.8"),
        ),
    )
    rejected = listing("145000").model_copy(update={"source_listing_id": "43"})
    rejected_result = repository.save_snapshot(rejected)
    repository.save_decision(
        "test:43",
        rejected_result[2],
        DealDecision(
            action=DecisionAction.REJECT,
            asking_price_aed=Decimal("145000"),
            market=None,
            costs=CostEstimate(),
            risks=RiskAssessment(),
            max_purchase_price_aed=Decimal("100000"),
            expected_profit_aed=Decimal("-45000"),
            roi_percent=Decimal("-31"),
            confidence=Decimal("0.8"),
        ),
    )

    decisions = repository.latest_decisions(limit=1)

    assert len(decisions) == 1
    assert decisions[0][1].action is DecisionAction.CONTACT

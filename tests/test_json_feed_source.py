from pathlib import Path

from src.domain.models import SourceConfiguration
from src.sources.json_feed import parse_json_feed
from src.storage import LocalRepository


def test_parse_json_feed_rejects_price_on_request_and_low_price() -> None:
    listings = parse_json_feed(
        "dealer_feed",
        {
            "items": [
                {
                    "id": "valid-1",
                    "url": "https://dealer.example/cars/valid-1",
                    "title": "2023 Toyota Yaris",
                    "price": "AED 45,000",
                    "make": "Toyota",
                    "model": "Yaris",
                    "year": 2023,
                    "images": ["https://dealer.example/images/valid-1.jpg"],
                },
                {
                    "id": "poa",
                    "url": "https://dealer.example/cars/poa",
                    "title": "2022 Toyota Camry",
                    "price": "Price on request",
                    "make": "Toyota",
                    "model": "Camry",
                },
                {
                    "id": "fake",
                    "url": "https://dealer.example/cars/fake",
                    "title": "2023 Toyota Yaris",
                    "price": 999,
                    "make": "Toyota",
                    "model": "Yaris",
                },
            ]
        },
    )

    assert [item.source_listing_id for item in listings] == ["valid-1"]
    assert str(listings[0].price_aed) == "45000"
    assert str(listings[0].image_urls[0]) == "https://dealer.example/images/valid-1.jpg"


def test_local_repository_persists_and_removes_dynamic_source(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "deal-sniper.db")
    config = SourceConfiguration(
        name="dealer_feed",
        url="https://dealer.example/vehicles.json",
        sample_count=12,
    )

    repository.save_source_configuration(config)

    loaded = repository.list_source_configurations()
    assert len(loaded) == 1
    assert loaded[0].name == "dealer_feed"
    assert repository.source_enabled("dealer_feed") is False
    assert repository.delete_source_configuration("dealer_feed") is True
    assert repository.list_source_configurations() == []

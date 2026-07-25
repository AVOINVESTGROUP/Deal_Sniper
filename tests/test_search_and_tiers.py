"""Проверки пользовательского поиска и границы Free/Pro."""

from decimal import Decimal

from src.bot import format_public_teaser
from src.domain.models import ListingSnapshot
from src.search import build_saved_search, parse_search


def test_bilingual_search_parses_only_explicit_filters() -> None:
    parsed = parse_search(
        "Toyota Camry 2020-2023 бюджет 100000 пробег 80000 GCC прибыль 7000 ROI 12",
        42,
        "ru",
    )

    assert parsed.settings.makes == ["Toyota"]
    assert parsed.settings.max_budget_aed == Decimal("100000")
    assert parsed.settings.min_year == 2020
    assert parsed.settings.max_year == 2023
    assert parsed.settings.max_mileage_km == 80000
    assert parsed.settings.specifications == ["GCC"]
    assert parsed.settings.min_profit_aed == Decimal("7000")
    assert parsed.settings.min_roi_percent == Decimal("12")
    assert build_saved_search("query", parsed).enabled is False


def test_free_teaser_does_not_leak_listing_or_financial_details() -> None:
    listing = ListingSnapshot(
        source="fixture",
        source_listing_id="secret-17",
        url="https://example.test/secret-17",
        title="2022 Toyota Camry",
        price_aed=Decimal("70000"),
        make="Toyota",
        model="Camry",
        year=2022,
    )

    teaser = format_public_teaser(listing)

    assert "Toyota Camry 2022" in teaser
    assert "secret-17" not in teaser
    assert "https://" not in teaser
    assert "70000" not in teaser
    assert "ROI" not in teaser

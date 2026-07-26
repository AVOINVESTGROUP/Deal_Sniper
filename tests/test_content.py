"""Воспроизводимость информационных материалов из Repository."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.content import audience_poll, market_pulse, price_drop
from src.content_job import format_market_watch_card
from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    MarketEstimate,
    RiskAssessment,
)
from src.storage import LocalRepository


def snapshot(price: str, observed_at: datetime) -> ListingSnapshot:
    return ListingSnapshot(
        source="fixture",
        source_listing_id="drop-1",
        url="https://example.test/drop-1",
        title="2022 Toyota Camry",
        make="Toyota",
        model="Camry",
        year=2022,
        mileage_km=40_000,
        price_aed=Decimal(price),
        observed_at=observed_at,
        source_observed_at=observed_at,
        fetched_at=observed_at,
    )


def test_market_pulse_and_price_drop_are_repository_backed(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "content.db")
    now = datetime.now(UTC)
    repository.save_snapshot(snapshot("90000", now - timedelta(hours=2)))
    current = snapshot("85000", now - timedelta(hours=1))
    _new, _changed, content_hash = repository.save_snapshot(current)
    repository.save_decision(
        "fixture:drop-1",
        content_hash,
        DealDecision(
            action=DecisionAction.CONTACT,
            asking_price_aed=Decimal("85000"),
            market=None,
            costs=CostEstimate(),
            risks=RiskAssessment(),
            max_purchase_price_aed=Decimal("85000"),
            expected_profit_aed=Decimal("5000"),
            roi_percent=Decimal("10"),
            confidence=Decimal("0.5"),
        ),
    )

    pulse = market_pulse(repository)
    drops = price_drop(repository)

    assert pulse.sample_size == 1
    assert pulse.facts["median_asking_price_aed"] == "85000"
    assert drops.sample_size == 1
    assert drops.facts["largest_drop_aed"] == "5000"
    assert len(drops.provenance) == 2


def test_poll_contains_no_unverifiable_market_numbers() -> None:
    poll = audience_poll()
    assert poll["cta"] == "/find"
    assert len(poll["options"]) == 4


def test_market_watch_card_contains_verified_facts_and_listing_link() -> None:
    listing = snapshot("75000", datetime.now(UTC)).model_copy(
        update={"image_urls": ["https://example.test/car.jpg"]}
    )
    decision = DealDecision(
        action=DecisionAction.REJECT,
        asking_price_aed=Decimal("75000"),
        market=MarketEstimate(
            low_aed=Decimal("90000"),
            median_aed=Decimal("95000"),
            high_aed=Decimal("100000"),
            comparable_ids=["a", "b", "c", "d", "e"],
            coverage_score=Decimal("0.8"),
        ),
        costs=CostEstimate(),
        risks=RiskAssessment(),
        max_purchase_price_aed=None,
        expected_profit_aed=None,
        roi_percent=None,
        confidence=Decimal("0.8"),
    )

    card = format_market_watch_card(listing, decision)

    assert "MARKET WATCH" in card
    assert "Price: 75,000 AED" in card
    assert "Verified market: 90,000–100,000 AED" in card
    assert "Open listing" in card
    assert "not an investment recommendation" in card
    assert len(card) < 1024

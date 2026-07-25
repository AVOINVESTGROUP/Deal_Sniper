"""Воспроизводимость информационных материалов из Repository."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.content import audience_poll, market_pulse, price_drop
from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
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

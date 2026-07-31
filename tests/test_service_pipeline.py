"""Интеграционная проверка нормализации, рынка, решения и идемпотентности."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.config import Settings
from src.domain.models import DecisionAction, ListingSnapshot, SellerType, VerificationStatus
from src.service import DealService
from src.storage import LocalRepository
from src.verification import PriceVerification


class FixtureSource:
    """Детерминированный источник для сквозного теста без сети."""

    def __init__(self, listings: list[ListingSnapshot]) -> None:
        self.listings = listings

    async def fetch(self) -> list[ListingSnapshot]:
        return self.listings


async def verify_fixture(listing: ListingSnapshot) -> PriceVerification:
    return PriceVerification(
        VerificationStatus.VERIFIED,
        listing.price_aed,
        "fixture verified",
        checksum_sha256="a" * 64,
        currency="AED",
    )


def camry(index: int, price: int) -> ListingSnapshot:
    return ListingSnapshot(
        source="fixture",
        source_listing_id=str(index),
        url=f"https://example.com/camry/{index}",
        title="2022 Toyota Camry SE GCC",
        price_aed=Decimal(price),
        observed_at=datetime.now(UTC),
        make="Toyota",
        model="Camry",
        trim="SE",
        specification="GCC",
        year=2022,
        mileage_km=40_000 + index * 1_000,
        seller_type=SellerType.PRIVATE,
    )


@pytest.mark.asyncio
async def test_pipeline_is_versioned_and_does_not_reprocess_unchanged_data(
    tmp_path: Path,
) -> None:
    settings = replace(
        Settings.from_env(),
        storage_backend="local",
        database_path=tmp_path / "pipeline.db",
        min_comparables_count=5,
    )
    listings = [camry(0, 60_000)] + [camry(index, 100_000 + index * 1_000) for index in range(1, 7)]
    service = DealService(
        settings,
        LocalRepository(settings.database_path),
        {"fixture": FixtureSource(listings)},
        verifier=verify_fixture,
    )

    first = await service.scan()
    second = await service.scan()

    assert first.new == 7
    assert len(first.decisions) == 7
    assert any(item.decision.action is DecisionAction.CONTACT for item in first.decisions)
    assert all(
        item.decision.decision_subject_id
        == f"{item.listing.source}:{item.listing.source_listing_id}"
        for item in first.decisions
    )
    funnel = service.repository.listing_pipeline_summary()
    assert funnel["fetched"] == 7
    assert funnel["verified"] == 7
    assert funnel["normalized"] == 7
    assert funnel["decision"] == 7
    assert 1 <= funnel["market"] <= funnel["decision"]
    assert funnel["eligible"] >= 1
    assert sum(funnel["actions"].values()) == 7
    for evaluated in first.decisions:
        await service.process_listing(
            f"{evaluated.listing.source}:{evaluated.listing.source_listing_id}",
            evaluated.content_hash,
        )
    recalculated_funnel = service.repository.listing_pipeline_summary()
    assert recalculated_funnel["market"] == 7
    assert second.new == 0
    assert second.changed == 0
    assert second.decisions == []


@pytest.mark.asyncio
async def test_processing_rejects_missing_exact_snapshot(tmp_path: Path) -> None:
    settings = replace(
        Settings.from_env(),
        storage_backend="local",
        database_path=tmp_path / "missing.db",
    )
    repository = LocalRepository(settings.database_path)
    service = DealService(
        settings,
        repository,
        {"fixture": FixtureSource([])},
        verifier=verify_fixture,
    )

    result = await service.process_listing("fixture:missing", "not-a-real-content-hash")

    assert result is None


@pytest.mark.asyncio
async def test_market_change_recalculates_existing_vehicle(tmp_path: Path) -> None:
    settings = replace(
        Settings.from_env(),
        storage_backend="local",
        database_path=tmp_path / "recalculation.db",
        min_comparables_count=5,
    )
    source = FixtureSource(
        [camry(0, 60_000)] + [camry(index, 100_000 + index * 1_000) for index in range(1, 7)]
    )
    service = DealService(
        settings,
        LocalRepository(settings.database_path),
        {"fixture": source},
        verifier=verify_fixture,
    )
    first = await service.scan()
    original = next(item for item in first.decisions if item.listing.source_listing_id == "0")

    source.listings[1] = camry(1, 130_000)
    second = await service.scan()
    recalculated = next(item for item in second.decisions if item.listing.source_listing_id == "0")

    assert original.decision.market_fingerprint != recalculated.decision.market_fingerprint
    assert original.decision.decision_id != recalculated.decision.decision_id

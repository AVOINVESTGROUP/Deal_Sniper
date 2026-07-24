"""Интеграционная проверка нормализации, рынка, решения и идемпотентности."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.config import Settings
from src.domain.models import DecisionAction, ListingSnapshot, SellerType
from src.service import DealService
from src.storage import LocalRepository


class FixtureSource:
    """Детерминированный источник для сквозного теста без сети."""

    def __init__(self, listings: list[ListingSnapshot]) -> None:
        self.listings = listings

    async def fetch(self) -> list[ListingSnapshot]:
        return self.listings


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
    )

    first = await service.scan()
    second = await service.scan()

    assert first.new == 7
    assert len(first.decisions) == 7
    assert any(item.decision.action is DecisionAction.CONTACT for item in first.decisions)
    assert second.new == 0
    assert second.changed == 0
    assert second.decisions == []

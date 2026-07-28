"""Контракты периодической и ручной сверки публикаций Pro R7.1."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from src.auth import Principal
from src.config import Settings
from src.domain.engines import DECISION_ENGINE_VERSION
from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    MarketEstimate,
    OutboxState,
    RiskAssessment,
)
from src.pro_publication import (
    preview_pro_reconciliation,
    reconcile_pro_publications,
)
from src.storage import LocalRepository


class FakeDispatcher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def enqueue_delivery(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def runtime_settings(monkeypatch: pytest.MonkeyPatch, *, limit: int = 10) -> Settings:
    monkeypatch.setenv("TELEGRAM_PRO_CHANNEL_ID", "-100777")
    monkeypatch.setenv("FINANCIAL_CONFIG_VERSION", "r71-config")
    monkeypatch.setenv("CHANNEL_MAX_POSTS_PER_RUN", str(limit))
    monkeypatch.setenv("TARGET_PROFIT_AED", "5000")
    monkeypatch.setenv("MIN_ROI_PERCENT", "10")
    return Settings.from_env()


def seed_candidate(
    repository: LocalRepository,
    *,
    source_listing_id: str,
    action: DecisionAction = DecisionAction.INSPECT,
) -> None:
    now = datetime.now(UTC)
    listing = ListingSnapshot(
        source="fixture",
        source_listing_id=source_listing_id,
        url=f"https://example.test/{source_listing_id}",
        title=f"2023 Toyota Camry {source_listing_id}",
        make="Toyota",
        model="Camry",
        year=2023,
        mileage_km=20_000,
        price_aed=Decimal("70000"),
        observed_at=now,
        fetched_at=now,
        image_urls=[f"https://example.test/{source_listing_id}.jpg"],
    )
    _new, _changed, content_hash = repository.save_snapshot(listing)
    repository.save_decision(
        f"fixture:{source_listing_id}",
        content_hash,
        DealDecision(
            action=action,
            asking_price_aed=listing.price_aed,
            market=MarketEstimate(
                low_aed=Decimal("90000"),
                median_aed=Decimal("95000"),
                high_aed=Decimal("100000"),
                comparable_ids=["a", "b", "c", "d", "e"],
                coverage_score=Decimal("0.8"),
            ),
            costs=CostEstimate(
                inspection_aed=Decimal("500"),
                registration_aed=Decimal("800"),
                repair_aed=Decimal("5000"),
                preparation_aed=Decimal("1700"),
            ),
            risks=RiskAssessment(warnings=["Trim is not stated"]),
            max_purchase_price_aed=Decimal("80000"),
            expected_profit_aed=Decimal("17000"),
            roi_percent=Decimal("21"),
            confidence=Decimal("0.7"),
            engine_version=DECISION_ENGINE_VERSION,
            decision_id=f"decision-{source_listing_id}",
            vehicle_id=f"vehicle-{source_listing_id}",
            content_hash=content_hash,
            financial_config_version="r71-config",
            verification_version="verification/v2",
            market_fingerprint=f"market-{source_listing_id}",
        ),
    )


@pytest.mark.asyncio
async def test_reconciliation_creates_once_requeues_pending_and_skips_sent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = LocalRepository(tmp_path / "r71.db")
    settings = runtime_settings(monkeypatch)
    seed_candidate(repository, source_listing_id="one")
    dispatcher = FakeDispatcher()

    first = await reconcile_pro_publications(repository, settings, dispatcher)
    second = await reconcile_pro_publications(repository, settings, dispatcher)
    delivery = repository.list_outbox(limit=1)[0]
    repository.update_outbox(delivery.delivery_id, OutboxState.SENT, telegram_message_id="42")
    third = await reconcile_pro_publications(repository, settings, dispatcher)

    assert first.created == 1 and first.selected == 1
    assert second.created == 0 and second.requeued == 1
    assert third.selected == 0 and third.skipped == 1
    assert len(repository.list_outbox(limit=10)) == 1
    assert len(dispatcher.payloads) == 2
    assert dispatcher.payloads[0]["image_url"].endswith("one.jpg")


@pytest.mark.asyncio
async def test_unknown_is_fail_closed_and_batch_limit_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = LocalRepository(tmp_path / "limit.db")
    settings = runtime_settings(monkeypatch, limit=1)
    seed_candidate(repository, source_listing_id="one")
    seed_candidate(repository, source_listing_id="two")
    dispatcher = FakeDispatcher()
    first = await reconcile_pro_publications(repository, settings, dispatcher)
    record = repository.list_outbox(limit=1)[0]
    repository.update_outbox(record.delivery_id, OutboxState.UNKNOWN, error="ambiguous")

    second = await reconcile_pro_publications(repository, settings, dispatcher)
    preview = preview_pro_reconciliation(repository, settings)

    assert first.selected == 1
    assert second.selected == 1
    assert second.created == 1
    assert preview.unknown == 1
    assert preview.missing == 0
    assert len(repository.list_outbox(limit=10)) == 2


@pytest.mark.asyncio
async def test_admin_previews_and_starts_allowlisted_publisher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "admin-r71.db")
    settings = runtime_settings(monkeypatch)
    seed_candidate(repository, source_listing_id="admin")
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(web, "runtime_settings", lambda: settings)
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(
            subject="owner", email="owner@example.com", admin=require_admin
        ),
    )
    calls: list[tuple[str, str]] = []

    def fake_run(project: str, region: str) -> dict[str, str]:
        calls.append((project, region))
        return {"job": "deal-sniper-publisher", "operation": "operations/1", "state": "STARTED"}

    monkeypatch.setattr(web, "run_publisher_job", fake_run)
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preview = await client.get("/admin/pro-publications")
        started = await client.post(
            "/admin/pro-publications/run",
            json={
                "operation_id": "operation-r71-admin",
                "confirmation": "PUBLISH 1 PRO",
            },
        )

    assert preview.status_code == 200
    assert preview.json()["missing"] == 1
    assert started.status_code == 200
    assert started.json()["started"] is True
    assert len(calls) == 1

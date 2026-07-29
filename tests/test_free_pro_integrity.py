"""Контракт Free → exact sent Pro без вымышленных или недоступных объектов."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.config import Settings
from src.domain.engines import DECISION_ENGINE_VERSION
from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    MarketEstimate,
    OutboxRecord,
    OutboxState,
    RiskAssessment,
)
from src.free_publication import FREE_TEMPLATE_VERSION, reconcile_free_publications
from src.pro_publication import current_pro_candidates
from src.storage import LocalRepository


class FakeDispatcher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def runtime_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-100111")
    monkeypatch.setenv("TELEGRAM_PRO_CHANNEL_ID", "-100222")
    monkeypatch.setenv("TELEGRAM_PRO_SUBSCRIPTION_URL", "https://t.me/+verified-pro")
    monkeypatch.setenv("FINANCIAL_CONFIG_VERSION", "integrity-v1")
    monkeypatch.setenv("TARGET_PROFIT_AED", "5000")
    monkeypatch.setenv("MIN_ROI_PERCENT", "10")
    monkeypatch.setenv("CHANNEL_MAX_POSTS_PER_RUN", "10")
    return Settings.from_env()


def seed_candidate(
    repository: LocalRepository,
    *,
    source_listing_id: str = "one",
    price: str = "70000",
    decision_id: str = "decision-one",
    action: DecisionAction = DecisionAction.INSPECT,
) -> tuple[str, str]:
    listing = ListingSnapshot(
        source="fixture",
        source_listing_id=source_listing_id,
        url=f"https://example.test/{source_listing_id}",
        title=f"2023 Toyota Camry {source_listing_id}",
        make="Toyota",
        model="Camry",
        year=2023,
        mileage_km=20_000,
        price_aed=Decimal(price),
        observed_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
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
            costs=CostEstimate(),
            risks=RiskAssessment(),
            max_purchase_price_aed=Decimal("80000"),
            expected_profit_aed=Decimal("17000"),
            roi_percent=Decimal("21"),
            confidence=Decimal("0.7"),
            engine_version=DECISION_ENGINE_VERSION,
            decision_id=decision_id,
            vehicle_id=f"vehicle-{source_listing_id}",
            content_hash=content_hash,
            financial_config_version="integrity-v1",
            verification_version="verification/v2",
            market_fingerprint=f"market-{decision_id}",
        ),
    )
    return f"fixture:{source_listing_id}", content_hash


def put_pro(
    repository: LocalRepository,
    settings: Settings,
    *,
    state: OutboxState,
    content_hash_override: str | None = None,
) -> OutboxRecord:
    candidate = current_pro_candidates(repository, settings)[0]
    record = OutboxRecord(
        delivery_id=candidate.delivery_id,
        decision_id=candidate.decision_id,
        recipient=settings.telegram_pro_channel_id or "",
        template_version="pro/v1",
        format="telegram",
        state=state,
        telegram_message_id="77" if state is OutboxState.SENT else None,
        payload={
            "decision_id": candidate.decision_id,
            "listing_id": candidate.listing_id,
            "content_hash": content_hash_override or candidate.decision.content_hash,
            "target_id": settings.telegram_pro_channel_id,
            "template_version": "pro/v1",
        },
    )
    return repository.put_outbox(record)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [OutboxState.PENDING, OutboxState.SENDING, OutboxState.FAILED, OutboxState.UNKNOWN],
)
async def test_free_is_blocked_until_exact_pro_is_sent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: OutboxState,
) -> None:
    repository = LocalRepository(tmp_path / f"blocked-{state.value}.db")
    settings = runtime_settings(monkeypatch)
    seed_candidate(repository)
    put_pro(repository, settings, state=state)
    dispatcher = FakeDispatcher()

    summary = await reconcile_free_publications(repository, settings, dispatcher)

    assert summary.created == 0
    assert summary.blocked_not_sent == 1
    assert dispatcher.payloads == []
    assert all(item.template_version != FREE_TEMPLATE_VERSION for item in repository.list_outbox())


@pytest.mark.asyncio
async def test_sent_exact_pro_creates_one_linked_free_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = LocalRepository(tmp_path / "sent.db")
    settings = runtime_settings(monkeypatch)
    _listing_id, content_hash = seed_candidate(repository)
    pro = put_pro(repository, settings, state=OutboxState.SENT)
    dispatcher = FakeDispatcher()

    first = await reconcile_free_publications(repository, settings, dispatcher)
    second = await reconcile_free_publications(repository, settings, dispatcher)
    free_records = [
        item
        for item in repository.list_outbox(limit=20)
        if item.template_version == FREE_TEMPLATE_VERSION
    ]

    assert first.created == 1
    assert second.created == 0 and second.requeued == 1
    assert len(free_records) == 1
    payload = free_records[0].payload
    assert payload["decision_id"] == pro.decision_id
    assert payload["content_hash"] == content_hash
    assert payload["parent_pro_delivery_id"] == pro.delivery_id
    assert payload["parent_pro_message_id"] == "77"
    assert payload["pro_object_button_url"] == "https://t.me/c/222/77"
    assert len(dispatcher.payloads) == 2


@pytest.mark.asyncio
async def test_revision_mismatch_and_price_change_are_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = LocalRepository(tmp_path / "mismatch.db")
    settings = runtime_settings(monkeypatch)
    seed_candidate(repository)
    put_pro(
        repository,
        settings,
        state=OutboxState.SENT,
        content_hash_override="invented-content-hash",
    )
    dispatcher = FakeDispatcher()

    mismatch = await reconcile_free_publications(repository, settings, dispatcher)
    seed_candidate(repository, price="68000", decision_id="decision-price-change")
    changed = await reconcile_free_publications(repository, settings, dispatcher)

    assert mismatch.blocked_revision_mismatch == 1
    assert changed.created == 0
    assert changed.blocked_no_pro == 1
    assert changed.blocked_revision_mismatch == 0
    assert dispatcher.payloads == []


@pytest.mark.asyncio
async def test_reject_is_never_advertised_in_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = LocalRepository(tmp_path / "reject.db")
    settings = runtime_settings(monkeypatch)
    seed_candidate(repository, action=DecisionAction.REJECT)
    dispatcher = FakeDispatcher()

    summary = await reconcile_free_publications(repository, settings, dispatcher)

    assert summary.pro_candidates == 0
    assert summary.created == 0
    assert dispatcher.payloads == []


@pytest.mark.asyncio
async def test_delivery_rechecks_exact_sent_parent_before_telegram(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "delivery-guard.db")
    settings = replace(
        runtime_settings(monkeypatch),
        delivery_enabled=True,
        internal_task_secret="",
        telegram_bot_token="test-token",
    )
    seed_candidate(repository)
    pro = put_pro(repository, settings, state=OutboxState.SENT)
    dispatcher = FakeDispatcher()
    await reconcile_free_publications(repository, settings, dispatcher)
    free = next(
        item
        for item in repository.list_outbox(limit=20)
        if item.template_version == FREE_TEMPLATE_VERSION
    )
    repository.update_outbox(pro.delivery_id, OutboxState.FAILED, error="withdrawn")
    monkeypatch.setattr(web, "settings", settings)
    monkeypatch.setattr(web, "runtime_settings", lambda: settings)
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))

    result = await web.deliver_content_task(
        web.ContentDeliveryTask.model_validate(free.payload),
        x_cloudtasks_taskname="integrity-task",
    )

    assert result == {"ok": True}
    assert repository.get_outbox(free.delivery_id).state is OutboxState.PENDING  # type: ignore[union-attr]
    audits = repository.list_audit_events(limit=10)
    assert any(item["event_type"] == "free_pro_integrity_block" for item in audits)


@pytest.mark.asyncio
async def test_delivery_sends_only_exact_linked_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "delivery-sent.db")
    settings = replace(
        runtime_settings(monkeypatch),
        delivery_enabled=True,
        internal_task_secret="",
        telegram_bot_token="test-token",
    )
    seed_candidate(repository)
    put_pro(repository, settings, state=OutboxState.SENT)
    dispatcher = FakeDispatcher()
    await reconcile_free_publications(repository, settings, dispatcher)
    free = next(
        item
        for item in repository.list_outbox(limit=20)
        if item.template_version == FREE_TEMPLATE_VERSION
    )
    sent_keyboards: list[object] = []

    class FakeBot:
        def __init__(self, _token: str) -> None:
            pass

        async def __aenter__(self) -> FakeBot:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def send_photo(self, **kwargs: object) -> SimpleNamespace:
            sent_keyboards.append(kwargs["reply_markup"])
            return SimpleNamespace(message_id=88)

    monkeypatch.setattr(web, "settings", settings)
    monkeypatch.setattr(web, "runtime_settings", lambda: settings)
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(web, "Bot", FakeBot)

    result = await web.deliver_content_task(
        web.ContentDeliveryTask.model_validate(free.payload),
        x_cloudtasks_taskname="integrity-task",
    )

    stored = repository.get_outbox(free.delivery_id)
    assert result == {"ok": True}
    assert stored is not None and stored.state is OutboxState.SENT
    assert stored.telegram_message_id == "88"
    assert len(sent_keyboards) == 1


@pytest.mark.asyncio
async def test_legacy_free_delivery_is_blocked_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "legacy-free-block.db")
    settings = replace(
        runtime_settings(monkeypatch),
        delivery_enabled=True,
        internal_task_secret="",
        telegram_bot_token="test-token",
    )
    monkeypatch.setattr(web, "settings", settings)
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    task = web.DeliveryTask(
        delivery_id="legacy-free-delivery",
        decision_id="decision-1",
        target_id=settings.telegram_channel_id,
        listing_id="listing-1",
        content_hash="content-1",
        text="legacy",
        engine_version="comparable-v3",
        template_version="free/v2",
    )

    result = await web.deliver_telegram_task(
        task,
        x_cloudtasks_taskname="legacy-free-task",
    )

    assert result == {"ok": True}
    audits = repository.list_audit_events(limit=10)
    assert audits[0]["payload"]["reason"] == "legacy_independent_free_template_disabled"


@pytest.mark.asyncio
async def test_legacy_object_market_watch_is_blocked_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "legacy-market-watch-block.db")
    settings = replace(
        runtime_settings(monkeypatch),
        delivery_enabled=True,
        internal_task_secret="",
        telegram_bot_token="test-token",
    )
    monkeypatch.setattr(web, "settings", settings)
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    task = web.ContentDeliveryTask(
        delivery_id="legacy-market-watch",
        publication_event_id="legacy-event",
        target_id=settings.telegram_channel_id,
        text="legacy",
        template_version="market-watch/v2",
    )

    result = await web.deliver_content_task(
        task,
        x_cloudtasks_taskname="legacy-market-watch-task",
    )

    assert result == {"ok": True}
    audits = repository.list_audit_events(limit=10)
    assert audits[0]["payload"]["reason"] == "legacy_independent_market_watch_disabled"

"""Проверки ротации, безопасности и идемпотентности Free → Pro CTA."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.bot import scan_and_publish, validate_free_publication
from src.config import Settings
from src.domain.engines import DECISION_ENGINE_VERSION
from src.domain.ids import delivery_id, publication_revision_id
from src.domain.models import (
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    MarketEstimate,
    OutboxRecord,
    PublicationEvent,
    RiskAssessment,
)
from src.firestore_storage import FirestoreRepository
from src.pro_cta import (
    append_pro_cta,
    pro_cta_count,
    pro_cta_for_index,
    validated_subscription_url,
)
from src.service import EvaluatedListing
from src.storage import LocalRepository
from src.web import publication_cta_keyboard


@pytest.mark.asyncio
async def test_legacy_full_card_publisher_never_falls_back_to_free_channel() -> None:
    """Legacy publisher обязан fail-closed без отдельного Pro-канала."""
    settings = replace(
        Settings.from_env(),
        telegram_channel_id="-100free",
        telegram_pro_channel_id=None,
    )

    with pytest.raises(RuntimeError, match="TELEGRAM_PRO_CHANNEL_ID"):
        await scan_and_publish(settings)


class FakeSnapshot:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self._payload = payload
        self.exists = payload is not None

    def to_dict(self) -> dict[str, object] | None:
        return self._payload


class FakeDocumentReference:
    def __init__(self, documents: dict[str, dict[str, object]], path: str) -> None:
        self.documents = documents
        self.path = path

    def get(self, transaction: object | None = None) -> FakeSnapshot:
        del transaction
        return FakeSnapshot(self.documents.get(self.path))


class FakeCollectionReference:
    def __init__(self, documents: dict[str, dict[str, object]], name: str) -> None:
        self.documents = documents
        self.name = name

    def document(self, document_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(self.documents, f"{self.name}/{document_id}")


class FakeTransaction:
    def set(
        self,
        reference: FakeDocumentReference,
        payload: dict[str, object],
        merge: bool = False,
    ) -> None:
        if merge and reference.path in reference.documents:
            reference.documents[reference.path].update(payload)
        else:
            reference.documents[reference.path] = payload


class FakeFirestoreClient:
    def __init__(self) -> None:
        self.documents: dict[str, dict[str, object]] = {}

    def collection(self, name: str) -> FakeCollectionReference:
        return FakeCollectionReference(self.documents, name)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


def test_approved_cta_pool_has_thirty_unique_variants() -> None:
    variants = [pro_cta_for_index(index) for index in range(pro_cta_count())]

    assert len(variants) >= 30
    assert len({item.variant_id for item in variants}) == len(variants)
    assert len({item.text for item in variants}) == len(variants)
    assert len({item.button_label for item in variants}) == len(variants)
    assert len({item.fingerprint for item in variants}) == len(variants)
    assert all(
        not any("\u0400" <= character <= "\u04ff" for character in item.text)
        for item in variants
    )


def test_repository_reserves_full_cycle_and_keeps_retry_stable(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "cta.db")
    count = pro_cta_count()

    assigned = [
        repository.reserve_pro_cta_variant(f"publication-{index}", count)
        for index in range(count)
    ]

    assert assigned == list(range(count))
    assert repository.reserve_pro_cta_variant("publication-7", count) == 7
    assert repository.reserve_pro_cta_variant("publication-next", count) == 0


def test_subscription_url_and_html_block_are_fail_closed() -> None:
    assert validated_subscription_url("https://t.me/+paid-channel")
    assert validated_subscription_url("https://telegram.me/$paid-channel")
    assert validated_subscription_url("http://t.me/+paid-channel") is None
    assert validated_subscription_url("https://example.com/pro") is None
    assert validated_subscription_url("https://t.me/") is None

    cta = pro_cta_for_index(0)
    rendered = append_pro_cta("<b>Car</b>", cta)
    assert rendered.startswith("<b>Car</b>")
    assert "<b>Go Pro</b>" in rendered
    assert cta.text in rendered


def test_publication_keyboard_contains_direct_subscription_button() -> None:
    keyboard = publication_cta_keyboard("Unlock full analysis", "https://t.me/+paid-channel")

    assert keyboard is not None
    assert keyboard.to_dict() == {
        "inline_keyboard": [
            [
                {
                    "text": "Unlock full analysis",
                    "url": "https://t.me/+paid-channel",
                }
            ]
        ]
    }
    assert publication_cta_keyboard("Upgrade", "https://example.com/pro") is None


def test_free_leakage_validator_rejects_financial_values_ids_and_links() -> None:
    validate_free_publication("<b>Toyota Camry 2022</b>\nVerified opportunity.")

    for leaked in (
        "Price: 75,000 AED",
        "Market: 90,000–100,000 AED",
        "ROI: 20%",
        "ID: dubicars:42",
        '<a href="https://example.test/car">Open listing</a>',
    ):
        with pytest.raises(ValueError, match="запрещённые Pro-данные"):
            validate_free_publication(leaked)


def test_publication_event_and_outbox_are_committed_atomically(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "publication.db")
    event = PublicationEvent(
        publication_event_id="free-revision-1",
        decision_id="decision-1",
        vehicle_id="vehicle-1",
        recipient="-1001",
        event_type="deal-candidate-free",
        template_version="free/v2",
        pro_cta_fingerprint="fingerprint-1",
    )
    payload: dict[str, object] = {
        "publication_event_id": event.publication_event_id,
        "text": "Safe teaser",
    }
    outbox = OutboxRecord(
        delivery_id="delivery-1",
        decision_id="decision-1",
        recipient="-1001",
        template_version="free/v2",
        format="telegram",
        payload=payload,
    )

    first = repository.commit_publication_with_outbox(event, outbox)
    second = repository.commit_publication_with_outbox(event, outbox)

    assert first.delivery_id == outbox.delivery_id
    assert second.payload == payload
    assert repository.get_outbox(outbox.delivery_id) is not None


def test_atomic_commit_detects_orphan_and_changed_retry(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "orphan.db")
    orphan = PublicationEvent(
        publication_event_id="orphan-event",
        decision_id="decision-1",
        vehicle_id="vehicle-1",
        event_type="legacy",
    )
    repository.save_publication_event(orphan)
    orphan_outbox = OutboxRecord(
        delivery_id="orphan-delivery",
        decision_id="decision-1",
        recipient="-1001",
        template_version="free/v2",
        format="telegram",
        payload={"publication_event_id": orphan.publication_event_id},
    )
    with pytest.raises(RuntimeError, match="Нарушена атомарность"):
        repository.commit_publication_with_outbox(orphan, orphan_outbox)

    event = orphan.model_copy(update={"publication_event_id": "stable-event"})
    outbox = orphan_outbox.model_copy(
        update={
            "delivery_id": "stable-delivery",
            "payload": {"publication_event_id": "stable-event", "text": "first"},
        }
    )
    repository.commit_publication_with_outbox(event, outbox)
    changed = outbox.model_copy(
        update={"payload": {"publication_event_id": "stable-event", "text": "changed"}}
    )
    with pytest.raises(RuntimeError, match="Retry изменил"):
        repository.commit_publication_with_outbox(event, changed)

    changed_event = event.model_copy(update={"recipient": "-1002"})
    with pytest.raises(RuntimeError, match="Retry изменил"):
        repository.commit_publication_with_outbox(changed_event, outbox)


def test_firestore_publication_bundle_and_cta_assignment_share_stable_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import firestore_storage

    monkeypatch.setattr(firestore_storage.firestore, "transactional", lambda function: function)
    client = FakeFirestoreClient()
    repository = FirestoreRepository.__new__(FirestoreRepository)
    repository.client = client  # type: ignore[assignment]
    count = pro_cta_count()

    assert repository.reserve_pro_cta_variant("revision-1", count) == 0
    assert repository.reserve_pro_cta_variant("revision-1", count) == 0
    assert repository.reserve_pro_cta_variant("revision-2", count) == 1
    event = PublicationEvent(
        publication_event_id="revision-1",
        decision_id="decision-1",
        vehicle_id="vehicle-1",
        recipient="-1001",
        event_type="deal-candidate-free",
        template_version="free/v2",
        pro_cta_fingerprint="fingerprint-1",
    )
    outbox = OutboxRecord(
        delivery_id="delivery-1",
        decision_id="decision-1",
        recipient="-1001",
        template_version="free/v2",
        format="telegram",
        payload={"publication_event_id": "revision-1", "text": "safe"},
    )

    first = repository.commit_publication_with_outbox(event, outbox)
    second = repository.commit_publication_with_outbox(event, outbox)

    assert first.payload == second.payload
    assert "publication_events/revision-1" in client.documents
    assert "delivery_outbox/delivery-1" in client.documents


@pytest.mark.asyncio
async def test_process_listing_creates_safe_atomic_free_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "process-free.db")
    listing = ListingSnapshot(
        source="fixture",
        source_listing_id="car-1",
        url="https://example.test/car-1",
        title="2022 Toyota Camry",
        make="Toyota",
        model="Camry",
        year=2022,
        price_aed=Decimal("60000"),
        observed_at=datetime.now(UTC),
    )
    decision = DealDecision(
        decision_id="decision-free-1",
        vehicle_id="vehicle-free-1",
        content_hash="content-free-1",
        action=DecisionAction.INSPECT,
        asking_price_aed=Decimal("60000"),
        market=MarketEstimate(
            low_aed=Decimal("100000"),
            median_aed=Decimal("105000"),
            high_aed=Decimal("110000"),
            comparable_ids=["a", "b", "c", "d", "e"],
            coverage_score=Decimal("0.8"),
        ),
        costs=CostEstimate(),
        risks=RiskAssessment(),
        max_purchase_price_aed=Decimal("70000"),
        expected_profit_aed=Decimal("10000"),
        roi_percent=Decimal("20"),
        confidence=Decimal("0.8"),
        engine_version=DECISION_ENGINE_VERSION,
    )
    evaluated = EvaluatedListing(listing, "content-free-1", decision)

    class FakeService:
        def __init__(self) -> None:
            self.repository = repository
            self.decision_engine = SimpleNamespace(version=DECISION_ENGINE_VERSION)

        async def process_listing(self, listing_id: str, content_hash: str) -> EvaluatedListing:
            assert (listing_id, content_hash) == ("fixture:car-1", "content-free-1")
            return evaluated

    sent_payloads: list[dict[str, Any]] = []

    class FakeDispatcher:
        def __init__(self, _settings: object) -> None:
            pass

        async def enqueue_delivery(self, payload: dict[str, Any]) -> None:
            sent_payloads.append(payload)

    test_settings = replace(
        web.settings,
        telegram_allowed_user_ids=frozenset(),
        telegram_channel_id="-100free",
        telegram_pro_channel_id=None,
        telegram_pro_subscription_url="https://t.me/+paid-channel",
        free_teaser_image_url="",
        target_profit_aed=Decimal("5000"),
        min_roi_percent=Decimal("10"),
        internal_task_secret="",
    )
    monkeypatch.setattr(web, "settings", test_settings)
    monkeypatch.setattr(web, "service", FakeService())
    monkeypatch.setattr(web, "CloudTaskDispatcher", FakeDispatcher)
    task = web.ProcessingTask(
        listing_id="fixture:car-1",
        content_hash="content-free-1",
        engine_version=DECISION_ENGINE_VERSION,
    )

    await web.process_listing_task(task, x_cloudtasks_taskname="task-1")
    await web.process_listing_task(task, x_cloudtasks_taskname="task-1")

    records = repository.list_outbox(limit=10)
    assert len(records) == 1
    assert len(sent_payloads) == 2
    assert sent_payloads[0] == sent_payloads[1]
    payload = records[0].payload
    text = str(payload["text"])
    validate_free_publication(text)
    assert "60,000" not in text
    assert "https://example.test" not in text
    assert payload["pro_cta_button_url"] == "https://t.me/+paid-channel"
    expected_event_id = publication_revision_id(
        decision_id_value="decision-free-1",
        vehicle_id="vehicle-free-1",
        event_type="deal-candidate-free",
        recipient_id="-100free",
        template_version="free/v2",
    )
    expected_delivery_id = delivery_id(
        decision_id_value=expected_event_id,
        recipient_id="-100free",
        template_version="free/v2",
        format_name="telegram",
    )
    assert payload["publication_event_id"] == expected_event_id
    assert records[0].delivery_id == expected_delivery_id
    with repository._connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM publication_events WHERE publication_event_id = ?",
            (payload["publication_event_id"],),
        ).fetchall()
    assert len(rows) == 1
    event = PublicationEvent.model_validate_json(rows[0]["payload_json"])
    assert event.recipient == "-100free"
    assert event.pro_cta_fingerprint == payload["pro_cta_fingerprint"]

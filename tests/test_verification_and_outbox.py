"""Контрактные тесты immutable evidence, freshness и delivery outbox."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from src.domain.models import (
    ListingSnapshot,
    OutboxRecord,
    OutboxState,
    ProcessingState,
    VerificationStatus,
)
from src.storage import LocalRepository, snapshot_hash
from src.verification import PriceVerification, build_evidence, extract_detail_prices


def listing() -> ListingSnapshot:
    return ListingSnapshot(
        source="fixture",
        source_listing_id="car-42",
        url="https://example.test/cars/car-42",
        title="2022 Toyota Camry SE",
        price_aed=Decimal("85000"),
        make="Toyota",
        model="Camry",
        year=2022,
        mileage_km=42_000,
    )


def test_same_semantic_evidence_only_extends_freshness() -> None:
    item = listing()
    result = PriceVerification(
        VerificationStatus.VERIFIED,
        Decimal("85000"),
        "verified",
        checksum_sha256="a" * 64,
        currency="AED",
    )
    first_at = datetime(2026, 7, 25, 10, tzinfo=UTC)
    first = build_evidence(item, snapshot_hash(item), result, now=first_at)
    refreshed = build_evidence(
        item,
        snapshot_hash(item),
        result,
        now=first_at + timedelta(minutes=10),
        previous=first,
    )

    assert refreshed.evidence_revision_id == first.evidence_revision_id
    assert refreshed.evidence_created_at == first.evidence_created_at
    assert refreshed.last_checked_at > first.last_checked_at
    assert refreshed.valid_until > first.valid_until
    assert refreshed.attempt_count == 2


def test_source_bound_extractor_rejects_unrelated_offer() -> None:
    html = """
    <script type="application/ld+json">
    {"@type":"Vehicle","sku":"other-1","offers":{"price":"1000","priceCurrency":"AED"}}
    </script>
    <script type="application/ld+json">
    {"@type":"Vehicle","sku":"car-42","offers":{"price":"85000","priceCurrency":"AED"}}
    </script>
    """

    assert extract_detail_prices(html, listing()) == [Decimal("85000")]


def test_outbox_sent_is_not_claimed_twice(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "outbox.db")
    original = OutboxRecord(
        delivery_id="delivery-1",
        decision_id="decision-1",
        recipient="recipient-1",
        template_version="pro/v1",
        format="telegram",
    )
    repository.put_outbox(original)
    claimed = repository.claim_outbox("delivery-1", "worker-1")

    assert claimed is not None
    assert claimed.state is OutboxState.SENDING

    repository.update_outbox("delivery-1", OutboxState.SENT, telegram_message_id="telegram-7")
    assert repository.claim_outbox("delivery-1", "worker-2") is None


def test_unknown_outbox_requires_explicit_single_reconciliation(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "unknown.db")
    repository.put_outbox(
        OutboxRecord(
            delivery_id="delivery-unknown",
            decision_id="decision-1",
            recipient="recipient-1",
            template_version="pro/v1",
            format="telegram",
            payload={"delivery_id": "delivery-unknown"},
        )
    )
    repository.update_outbox("delivery-unknown", OutboxState.UNKNOWN, error="timeout")

    reconciled = repository.reconcile_outbox("delivery-unknown", "retry_once", "operation-1")

    assert reconciled is not None
    assert reconciled.state is OutboxState.PENDING
    assert reconciled.retry_once_used
    assert reconciled.audit_events[-1]["operation_id"] == "operation-1"


def test_telegram_update_state_machine_allows_failed_retry(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "telegram-update.db")

    assert repository.claim_telegram_update(42, "revision-a")
    assert not repository.claim_telegram_update(42, "revision-b")
    repository.finish_telegram_update(42, ProcessingState.FAILED, "temporary")
    assert repository.claim_telegram_update(42, "revision-c")
    repository.finish_telegram_update(42, ProcessingState.COMPLETED)
    assert not repository.claim_telegram_update(42, "revision-d")

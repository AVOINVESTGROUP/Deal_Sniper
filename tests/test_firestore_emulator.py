"""Интеграционные проверки настоящих Firestore-транзакций R6."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from src.domain.models import OutboxRecord, PublicationEvent
from src.firestore_storage import FirestoreRepository

FIRESTORE_TEST_DATABASE = os.getenv("FIRESTORE_INTEGRATION_DATABASE", "").strip()
FIRESTORE_TEST_PROJECT = os.getenv("FIRESTORE_INTEGRATION_PROJECT", "").strip()

pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST") and not FIRESTORE_TEST_DATABASE,
    reason="Требуется Firestore emulator или явная FIRESTORE_INTEGRATION_DATABASE",
)


def test_firestore_transaction_is_atomic_and_cta_rotation_is_concurrent_safe() -> None:
    """Firestore подтверждает atomic bundle и сериализацию CTA allocator."""
    project = FIRESTORE_TEST_PROJECT or "deal-sniper-r6-emulator"
    database = FIRESTORE_TEST_DATABASE or "(default)"
    repository = FirestoreRepository(project_id=project, database=database)
    prefix = f"r6-{uuid4().hex}"
    revision_ids = [f"{prefix}-revision-{index}" for index in range(12)]
    event_id = f"{prefix}-revision-atomic"
    delivery_id = f"{prefix}-delivery-atomic"
    state_ref = repository.client.collection("publication_control").document("pro_cta")
    original_state_snapshot = state_ref.get()
    original_state = original_state_snapshot.to_dict()

    try:
        with ThreadPoolExecutor(max_workers=12) as executor:
            variants = list(
                executor.map(
                    lambda revision_id: repository.reserve_pro_cta_variant(revision_id, 30),
                    revision_ids,
                )
            )

        assert len(set(variants)) == len(revision_ids)
        assert repository.reserve_pro_cta_variant(revision_ids[0], 30) == variants[0]

        event = PublicationEvent(
            publication_event_id=event_id,
            decision_id=f"{prefix}-decision",
            vehicle_id=f"{prefix}-vehicle",
            recipient="-100free",
            event_type="deal-candidate-free",
            template_version="free/v2",
            pro_cta_fingerprint="fingerprint-atomic",
        )
        outbox = OutboxRecord(
            delivery_id=delivery_id,
            decision_id=f"{prefix}-decision",
            recipient="-100free",
            template_version="free/v2",
            format="telegram",
            payload={
                "publication_event_id": event_id,
                "text": "Verified opportunity. Unlock Pro analysis.",
            },
        )

        first = repository.commit_publication_with_outbox(event, outbox)
        second = repository.commit_publication_with_outbox(event, outbox)

        assert first.payload == second.payload
        assert repository.get_outbox(delivery_id) is not None
        event_snapshot = repository.client.collection("publication_events").document(event_id).get()
        assert event_snapshot.exists

        changed_event = event.model_copy(update={"recipient": "-100other"})
        with pytest.raises(RuntimeError, match="Retry изменил"):
            repository.commit_publication_with_outbox(changed_event, outbox)
    finally:
        for revision_id in revision_ids:
            repository.client.collection("pro_cta_assignments").document(revision_id).delete()
        repository.client.collection("publication_events").document(event_id).delete()
        repository.client.collection("delivery_outbox").document(delivery_id).delete()
        if original_state_snapshot.exists and original_state is not None:
            state_ref.set(original_state)
        else:
            state_ref.delete()

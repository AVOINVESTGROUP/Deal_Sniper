"""Production-хранилище объявлений и решений в Cloud Firestore."""

import hashlib
from datetime import UTC, datetime

from google.cloud import firestore

from src.domain.models import DealDecision, ListingSnapshot
from src.storage import snapshot_hash


class FirestoreRepository:
    """Firestore-реализация контракта Repository."""

    def __init__(self, project_id: str, database: str = "(default)") -> None:
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT обязателен для Firestore")
        self.client = firestore.Client(project=project_id, database=database)

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]:
        listing_id = f"{snapshot.source}:{snapshot.source_listing_id}"
        content_hash = snapshot_hash(snapshot)
        listing_ref = self.client.collection("listings").document(listing_id)
        snapshot_ref = listing_ref.collection("snapshots").document(content_hash)
        current = listing_ref.get()
        current_data = current.to_dict() or {}
        if current.exists and current_data.get("content_hash") == content_hash:
            return False, False, content_hash

        previous_price = current_data.get("price_aed")
        payload = snapshot.model_dump(mode="json")
        batch = self.client.batch()
        batch.set(
            snapshot_ref,
            {
                "listing_id": listing_id,
                "content_hash": content_hash,
                "observed_at": snapshot.observed_at,
                "price_aed": str(snapshot.price_aed),
                "payload": payload,
            },
        )
        batch.set(
            listing_ref,
            {
                "listing_id": listing_id,
                "source": snapshot.source,
                "source_listing_id": snapshot.source_listing_id,
                "content_hash": content_hash,
                "price_aed": str(snapshot.price_aed),
                "updated_at": snapshot.observed_at,
                "payload": payload,
            },
        )
        batch.commit()
        price_changed = current.exists and previous_price != str(snapshot.price_aed)
        return not current.exists, price_changed, content_hash

    def latest_snapshots(self) -> list[ListingSnapshot]:
        results: list[ListingSnapshot] = []
        for document in self.client.collection("listings").stream():
            data = document.to_dict()
            if data and "payload" in data:
                results.append(ListingSnapshot.model_validate(data["payload"]))
        return results

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        self.client.collection("decisions").document(_stable_id(listing_id, content_hash)).set(
            {
                "listing_id": listing_id,
                "content_hash": content_hash,
                "created_at": datetime.now(UTC),
                "payload": decision.model_dump(mode="json"),
            }
        )

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]:
        documents = list(self.client.collection("decisions").stream())

        def created_at(document: firestore.DocumentSnapshot) -> datetime:
            data = document.to_dict() or {}
            value = data.get("created_at")
            return value if isinstance(value, datetime) else datetime.min.replace(tzinfo=UTC)

        documents.sort(key=created_at, reverse=True)
        results: list[tuple[ListingSnapshot, DealDecision]] = []
        for document in documents[:limit]:
            data = document.to_dict() or {}
            if "listing_id" not in data or "payload" not in data:
                continue
            listing = self.client.collection("listings").document(data["listing_id"]).get()
            listing_data = listing.to_dict()
            if listing_data:
                results.append(
                    (
                        ListingSnapshot.model_validate(listing_data["payload"]),
                        DealDecision.model_validate(data["payload"]),
                    )
                )
        return results

    def count_snapshots(self) -> int:
        return sum(1 for _document in self.client.collection_group("snapshots").stream())

    def notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> bool:
        return (
            self.client.collection("notifications")
            .document(_stable_id(target_id, listing_id, content_hash))
            .get()
            .exists
        )

    def mark_notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> None:
        self.client.collection("notifications").document(
            _stable_id(target_id, listing_id, content_hash)
        ).set(
            {
                "target_id": target_id,
                "listing_id": listing_id,
                "content_hash": content_hash,
                "sent_at": datetime.now(UTC),
            }
        )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

"""Production-хранилище объявлений и решений в Cloud Firestore."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from src.domain.models import (
    DealDecision,
    ListingSnapshot,
    NormalizedVehicle,
    RawSnapshotMetadata,
    UserAction,
    UserSettings,
    VehicleIdentity,
)
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

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None:
        document = self.client.collection("listings").document(listing_id).get()
        data = document.to_dict()
        return ListingSnapshot.model_validate(data["payload"]) if data else None

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        self.client.collection("decisions").document(
            _stable_id(listing_id, content_hash, decision.engine_version)
        ).set(
            {
                "listing_id": listing_id,
                "content_hash": content_hash,
                "engine_version": decision.engine_version,
                "created_at": datetime.now(UTC),
                "payload": decision.model_dump(mode="json"),
            }
        )

    def decision_exists(
        self, listing_id: str, content_hash: str, engine_version: str
    ) -> bool:
        return (
            self.client.collection("decisions")
            .document(_stable_id(listing_id, content_hash, engine_version))
            .get()
            .exists
        )

    def save_normalized_vehicle(self, vehicle: NormalizedVehicle) -> None:
        self.client.collection("normalized_vehicles").document(vehicle.listing_id).set(
            {
                "listing_id": vehicle.listing_id,
                "comparison_key": vehicle.comparison_key,
                "updated_at": datetime.now(UTC),
                "payload": vehicle.model_dump(mode="json"),
            }
        )

    def normalized_vehicles(self) -> list[NormalizedVehicle]:
        results: list[NormalizedVehicle] = []
        for document in self.client.collection("normalized_vehicles").stream():
            data = document.to_dict()
            if data and "payload" in data:
                results.append(NormalizedVehicle.model_validate(data["payload"]))
        return results

    def save_vehicle_identity(self, identity: VehicleIdentity) -> None:
        self.client.collection("vehicle_identities").document(identity.vehicle_id).set(
            {
                "vehicle_id": identity.vehicle_id,
                "listing_ids": identity.listing_ids,
                "comparison_key": identity.comparison_key,
                "updated_at": datetime.now(UTC),
                "payload": identity.model_dump(mode="json"),
            }
        )

    def save_normalized_market(
        self,
        vehicles: list[NormalizedVehicle],
        identities: list[VehicleIdentity],
    ) -> None:
        """Сохраняет рынок пакетами ниже лимита 500 операций Firestore."""
        batch = self.client.batch()
        operation_count = 0

        def commit_if_needed() -> None:
            nonlocal batch, operation_count
            if operation_count >= 400:
                batch.commit()
                batch = self.client.batch()
                operation_count = 0

        for vehicle in vehicles:
            reference = self.client.collection("normalized_vehicles").document(
                vehicle.listing_id
            )
            batch.set(
                reference,
                {
                    "listing_id": vehicle.listing_id,
                    "comparison_key": vehicle.comparison_key,
                    "updated_at": datetime.now(UTC),
                    "payload": vehicle.model_dump(mode="json"),
                },
            )
            operation_count += 1
            commit_if_needed()
        for identity in identities:
            reference = self.client.collection("vehicle_identities").document(
                identity.vehicle_id
            )
            batch.set(
                reference,
                {
                    "vehicle_id": identity.vehicle_id,
                    "listing_ids": identity.listing_ids,
                    "comparison_key": identity.comparison_key,
                    "updated_at": datetime.now(UTC),
                    "payload": identity.model_dump(mode="json"),
                },
            )
            operation_count += 1
            commit_if_needed()
        if operation_count:
            batch.commit()

    def save_raw_snapshot(self, metadata: RawSnapshotMetadata) -> None:
        document_id = _stable_id(
            metadata.source,
            str(metadata.source_url),
            metadata.checksum_sha256,
        )
        self.client.collection("raw_snapshots").document(document_id).set(
            metadata.model_dump(mode="json")
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
            listing = (
                self.client.collection("listings")
                .document(data["listing_id"])
                .collection("snapshots")
                .document(data["content_hash"])
                .get()
            )
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

    def source_enabled(self, source_name: str, default: bool = True) -> bool:
        """Читает переключатель источника из централизованного реестра Firestore."""
        document = self.client.collection("source_registry").document(source_name).get()
        data = document.to_dict() or {}
        value = data.get("enabled")
        return value if isinstance(value, bool) else default

    def set_source_enabled(self, source_name: str, enabled: bool) -> None:
        """Сохраняет переключатель источника, доступный API и фоновым задачам."""
        self.client.collection("source_registry").document(source_name).set(
            {
                "source_name": source_name,
                "enabled": enabled,
                "updated_at": datetime.now(UTC),
            },
            merge=True,
        )

    def record_source_run(self, source_name: str, payload: dict[str, Any]) -> None:
        self.client.collection("source_registry").document(source_name).set(
            {"last_run": payload, "updated_at": datetime.now(UTC)},
            merge=True,
        )

    def source_health(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for document in self.client.collection("source_registry").stream():
            data = document.to_dict() or {}
            last_run = data.get("last_run")
            if isinstance(last_run, dict):
                results[document.id] = last_run
        return results

    def claim_telegram_update(self, update_id: int) -> bool:
        """Атомарно блокирует повторную обработку webhook-доставки Telegram."""
        try:
            self.client.collection("telegram_updates").document(str(update_id)).create(
                {
                    "update_id": update_id,
                    "claimed_at": datetime.now(UTC),
                }
            )
        except AlreadyExists:
            return False
        return True

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        document = self.client.collection("user_settings").document(str(user_id)).get()
        data = document.to_dict()
        return UserSettings.model_validate(data) if data else None

    def save_user_settings(self, settings: UserSettings) -> None:
        self.client.collection("user_settings").document(str(settings.user_id)).set(
            settings.model_dump(mode="json")
        )

    def save_user_action(self, action: UserAction) -> None:
        document_id = _stable_id(str(action.user_id), action.listing_id)
        self.client.collection("user_actions").document(document_id).set(
            action.model_dump(mode="json")
        )

    def user_watchlist(self, user_id: int) -> list[str]:
        documents = self.client.collection("user_actions").stream()
        return [
            str(data["listing_id"])
            for document in documents
            if (data := document.to_dict()) and data.get("action") == "WATCH"
        ]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

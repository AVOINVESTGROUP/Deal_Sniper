"""Production-хранилище объявлений и решений в Cloud Firestore."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from src.domain.ids import canonical_hash
from src.domain.models import (
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    NormalizedVehicle,
    OutboxRecord,
    OutboxState,
    Outcome,
    ProcessingState,
    PublicationEvent,
    RawSnapshotMetadata,
    SavedSearch,
    TelegramUpdateRecord,
    UserAction,
    UserSettings,
    VehicleIdentity,
    VerificationEvidence,
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
        transaction = self.client.transaction()

        @firestore.transactional
        def persist(transaction: firestore.Transaction) -> tuple[bool, bool]:
            current = listing_ref.get(transaction=transaction)
            current_data = current.to_dict() or {}
            if current.exists and current_data.get("content_hash") == content_hash:
                transaction.set(
                    listing_ref,
                    {"last_seen_at": firestore.SERVER_TIMESTAMP},
                    merge=True,
                )
                return False, False
            sequence = snapshot.version_sequence
            if sequence is None:
                sequence = int(current_data.get("version_sequence", 0)) + 1
            source_observed_at = snapshot.source_observed_at or snapshot.observed_at
            current_key = (
                int(current_data.get("version_sequence", -1)),
                str(current_data.get("source_observed_at", "")),
                str(current_data.get("fetched_at", "")),
                str(current_data.get("tie_breaker", "")),
            )
            candidate_key = (
                sequence,
                source_observed_at.isoformat(),
                snapshot.fetched_at.isoformat(),
                content_hash,
            )
            stored = snapshot.model_copy(update={"version_sequence": sequence})
            payload = stored.model_dump(mode="json")
            transaction.set(
                snapshot_ref,
                {
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "source_observed_at": source_observed_at,
                    "fetched_at": snapshot.fetched_at,
                    "ingested_at": firestore.SERVER_TIMESTAMP,
                    "version_sequence": sequence,
                    "price_aed": str(snapshot.price_aed),
                    "payload": payload,
                    "schema_version": "listing-snapshot/v2",
                },
            )
            if not current.exists or candidate_key > current_key:
                transaction.set(
                    listing_ref,
                    {
                        "listing_id": listing_id,
                        "source": snapshot.source,
                        "source_listing_id": snapshot.source_listing_id,
                        "content_hash": content_hash,
                        "price_aed": str(snapshot.price_aed),
                        "source_observed_at": source_observed_at.isoformat(),
                        "fetched_at": snapshot.fetched_at.isoformat(),
                        "ingested_at": firestore.SERVER_TIMESTAMP,
                        "last_seen_at": firestore.SERVER_TIMESTAMP,
                        "version_sequence": sequence,
                        "tie_breaker": content_hash,
                        "lifecycle": "changed" if current.exists else "active",
                        "payload": payload,
                        "schema_version": "listing-current/v2",
                    },
                )
            return not current.exists, (
                current.exists and current_data.get("price_aed") != str(snapshot.price_aed)
            )

        is_new, price_changed = persist(transaction)
        return is_new, price_changed, content_hash

    def save_snapshots(
        self,
        snapshots: list[ListingSnapshot],
    ) -> list[tuple[ListingSnapshot, bool, bool, str]]:
        """Сохраняет каждую версию транзакционно, исключая out-of-order pointer race."""
        return [(snapshot, *self.save_snapshot(snapshot)) for snapshot in snapshots]

    def latest_snapshots(self) -> list[ListingSnapshot]:
        results: list[ListingSnapshot] = []
        for document in self.client.collection("listings").stream():
            data = document.to_dict()
            if data and "payload" in data:
                results.append(ListingSnapshot.model_validate(data["payload"]))
        return results

    def snapshot_versions(self) -> list[ListingSnapshot]:
        results: list[ListingSnapshot] = []
        for document in self.client.collection_group("snapshots").stream():
            data = document.to_dict() or {}
            if "payload" in data:
                results.append(ListingSnapshot.model_validate(data["payload"]))
        return sorted(results, key=lambda item: item.observed_at, reverse=True)

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None:
        document = self.client.collection("listings").document(listing_id).get()
        data = document.to_dict()
        return ListingSnapshot.model_validate(data["payload"]) if data else None

    def get_snapshot(self, listing_id: str, content_hash: str) -> ListingSnapshot | None:
        """Читает точную версию, указанную processing task."""
        document = (
            self.client.collection("listings")
            .document(listing_id)
            .collection("snapshots")
            .document(content_hash)
            .get()
        )
        data = document.to_dict()
        if not data or data.get("content_hash") != content_hash:
            return None
        return ListingSnapshot.model_validate(data["payload"])

    def is_current_snapshot(self, listing_id: str, content_hash: str) -> bool:
        data = self.client.collection("listings").document(listing_id).get().to_dict() or {}
        return data.get("content_hash") == content_hash and data.get("lifecycle", "active") in {
            "active",
            "changed",
        }

    def get_verification_evidence(self, verification_key: str) -> VerificationEvidence | None:
        document = self.client.collection("verification_evidence").document(verification_key).get()
        data = document.to_dict()
        return VerificationEvidence.model_validate(data["payload"]) if data else None

    def save_verification_evidence(self, evidence: VerificationEvidence) -> None:
        self.client.collection("verification_evidence").document(evidence.verification_key).set(
            {
                "verification_key": evidence.verification_key,
                "evidence_revision_id": evidence.evidence_revision_id,
                "status": evidence.status.value,
                "freshness_status": evidence.freshness_status.value,
                "valid_until": evidence.valid_until,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "payload": evidence.model_dump(mode="json"),
                "schema_version": "verification-evidence/v1",
            }
        )

    def put_outbox(self, record: OutboxRecord) -> OutboxRecord:
        reference = self.client.collection("delivery_outbox").document(record.delivery_id)
        try:
            reference.create(
                {
                    "delivery_id": record.delivery_id,
                    "state": record.state.value,
                    "payload": record.model_dump(mode="json"),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "schema_version": "outbox/v2",
                }
            )
            return record
        except AlreadyExists:
            data = reference.get().to_dict()
            if not data:
                raise RuntimeError("Запись outbox исчезла после AlreadyExists") from None
            return OutboxRecord.model_validate(data["payload"])

    def claim_outbox(
        self, delivery_id: str, lease_owner: str, lease_seconds: int = 120
    ) -> OutboxRecord | None:
        reference = self.client.collection("delivery_outbox").document(delivery_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def claim(transaction: firestore.Transaction) -> OutboxRecord | None:
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return None
            data = snapshot.to_dict() or {}
            record = OutboxRecord.model_validate(data["payload"])
            now = datetime.now(UTC)
            leased = record.lease_expires_at is not None and record.lease_expires_at > now
            if record.state in {OutboxState.SENT, OutboxState.UNKNOWN} or (
                record.state is OutboxState.SENDING and leased
            ):
                return None
            claimed = record.model_copy(
                update={
                    "state": OutboxState.SENDING,
                    "attempt_id": f"{delivery_id}:{int(now.timestamp() * 1000)}",
                    "lease_owner": lease_owner,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                    "last_attempt_at": now,
                    "updated_at": now,
                }
            )
            transaction.set(
                reference,
                {
                    "state": claimed.state.value,
                    "payload": claimed.model_dump(mode="json"),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return claimed

        return cast(OutboxRecord | None, claim(transaction))

    def update_outbox(
        self,
        delivery_id: str,
        state: OutboxState,
        *,
        error: str | None = None,
        telegram_message_id: str | None = None,
        provider_message_id: str | None = None,
    ) -> None:
        reference = self.client.collection("delivery_outbox").document(delivery_id)
        snapshot = reference.get()
        data = snapshot.to_dict()
        if not data:
            return
        record = OutboxRecord.model_validate(data["payload"])
        updated = record.model_copy(
            update={
                "state": state,
                "last_error": error,
                "telegram_message_id": telegram_message_id,
                "provider_message_id": provider_message_id or telegram_message_id,
                "lease_owner": None,
                "lease_expires_at": None,
                "updated_at": datetime.now(UTC),
            }
        )
        reference.set(
            {
                "state": state.value,
                "payload": updated.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def get_outbox(self, delivery_id: str) -> OutboxRecord | None:
        data = self.client.collection("delivery_outbox").document(delivery_id).get().to_dict()
        return OutboxRecord.model_validate(data["payload"]) if data else None

    def list_outbox(self, state: OutboxState | None = None, limit: int = 100) -> list[OutboxRecord]:
        query: Any = self.client.collection("delivery_outbox")
        if state is not None:
            query = query.where("state", "==", state.value)
        return [
            OutboxRecord.model_validate(data["payload"])
            for document in query.limit(limit).stream()
            if (data := document.to_dict()) and "payload" in data
        ]

    def reconcile_outbox(
        self, delivery_id: str, action: str, operation_id: str
    ) -> OutboxRecord | None:
        target_state = {
            "mark_sent": OutboxState.SENT,
            "mark_failed": OutboxState.FAILED,
            "retry_once": OutboxState.PENDING,
        }.get(action)
        if target_state is None:
            raise ValueError("Неизвестное действие reconciliation")
        reference = self.client.collection("delivery_outbox").document(delivery_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def reconcile(transaction: firestore.Transaction) -> OutboxRecord | None:
            snapshot = reference.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            if not snapshot.exists:
                return None
            record = OutboxRecord.model_validate(data["payload"])
            if record.state is not OutboxState.UNKNOWN:
                raise ValueError("Reconciliation разрешена только для unknown")
            if action == "retry_once" and record.retry_once_used:
                raise ValueError("Повторная ручная отправка уже использована")
            now = datetime.now(UTC)
            event = {"operation_id": operation_id, "action": action, "at": now.isoformat()}
            updated = record.model_copy(
                update={
                    "state": target_state,
                    "retry_once_used": record.retry_once_used or action == "retry_once",
                    "last_error": None if action == "retry_once" else record.last_error,
                    "audit_events": [*record.audit_events, event],
                    "updated_at": now,
                }
            )
            transaction.set(
                reference,
                {
                    "state": target_state.value,
                    "payload": updated.model_dump(mode="json"),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return updated

        result = cast(OutboxRecord | None, reconcile(transaction))
        if result is not None:
            self.record_audit_event(
                "outbox_reconciliation",
                {"delivery_id": delivery_id, "operation_id": operation_id, "action": action},
            )
        return result

    def save_search(self, search: SavedSearch) -> None:
        self.client.collection("saved_searches").document(search.search_id).set(
            {
                "search_id": search.search_id,
                "user_id": search.user_id,
                "enabled": search.enabled,
                "payload": search.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "schema_version": "saved-search/v1",
            }
        )

    def user_searches(self, user_id: int) -> list[SavedSearch]:
        query = self.client.collection("saved_searches").where("user_id", "==", user_id)
        return [
            SavedSearch.model_validate(data["payload"])
            for document in query.stream()
            if (data := document.to_dict()) and "payload" in data
        ]

    def active_searches(self) -> list[SavedSearch]:
        query = self.client.collection("saved_searches").where("enabled", "==", True)
        return [
            SavedSearch.model_validate(data["payload"])
            for document in query.stream()
            if (data := document.to_dict()) and "payload" in data
        ]

    def set_search_enabled(self, user_id: int, search_id: str, enabled: bool) -> bool:
        reference = self.client.collection("saved_searches").document(search_id)
        transaction = self.client.transaction()

        @firestore.transactional
        def update(transaction: firestore.Transaction) -> bool:
            snapshot = reference.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            if not snapshot.exists or data.get("user_id") != user_id:
                return False
            search = SavedSearch.model_validate(data["payload"])
            updated = search.model_copy(update={"enabled": enabled})
            transaction.set(
                reference,
                {
                    "enabled": enabled,
                    "payload": updated.model_dump(mode="json"),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return True

        return cast(bool, update(transaction))

    def save_outcome(self, outcome: Outcome) -> None:
        document_id = _stable_id(
            str(outcome.user_id), outcome.listing_id, outcome.decision_content_hash
        )
        self.client.collection("outcomes").document(document_id).set(
            {
                "user_id": outcome.user_id,
                "listing_id": outcome.listing_id,
                "decision_content_hash": outcome.decision_content_hash,
                "payload": outcome.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "schema_version": "outcome/v1",
            }
        )

    def user_outcomes(self, user_id: int) -> list[Outcome]:
        query = self.client.collection("outcomes").where("user_id", "==", user_id)
        return [
            Outcome.model_validate(data["payload"])
            for document in query.stream()
            if (data := document.to_dict()) and "payload" in data
        ]

    def save_publication_event(self, event: PublicationEvent) -> None:
        try:
            self.client.collection("publication_events").document(
                event.publication_event_id
            ).create(
                {
                    "publication_event_id": event.publication_event_id,
                    "decision_id": event.decision_id,
                    "vehicle_id": event.vehicle_id,
                    "event_type": event.event_type,
                    "payload": event.model_dump(mode="json"),
                    "created_at": event.created_at,
                    "schema_version": "publication-event/v1",
                }
            )
        except AlreadyExists:
            return

    def admin_summary(self) -> dict[str, Any]:
        collections = {
            "users": "user_settings",
            "searches": "saved_searches",
            "outbox": "delivery_outbox",
            "audit_events": "audit_events",
            "quarantine": "verification_evidence",
            "current_decisions": "current_decisions",
            "outcomes": "outcomes",
        }
        counts = {
            name: sum(1 for _document in self.client.collection(collection).stream())
            for name, collection in collections.items()
        }
        outbox_states: dict[str, int] = {}
        for document in self.client.collection("delivery_outbox").stream():
            state = str((document.to_dict() or {}).get("state", "unknown"))
            outbox_states[state] = outbox_states.get(state, 0) + 1
        return {"counts": counts, "outbox_states": outbox_states}

    def schema_version(self) -> str:
        data = self.client.collection("schema_ledger").document("current").get().to_dict()
        return str((data or {}).get("schema_version", "legacy"))

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        immutable_id = decision.decision_id or _stable_id(
            listing_id, content_hash, decision.engine_version
        )
        subject_id = listing_id
        decision_ref = self.client.collection("decisions").document(immutable_id)
        current_ref = self.client.collection("current_decisions").document(subject_id)
        processing_ref = self.client.collection("decision_processing_keys").document(
            _stable_id(listing_id, content_hash, decision.engine_version)
        )
        transaction = self.client.transaction()

        @firestore.transactional
        def persist(transaction: firestore.Transaction) -> None:
            previous = current_ref.get(transaction=transaction)
            previous_data = previous.to_dict() or {}
            previous_id = previous_data.get("decision_id")
            if previous_id and previous_id != immutable_id:
                transaction.set(
                    self.client.collection("decisions").document(str(previous_id)),
                    {"is_current": False, "superseded_by": immutable_id},
                    merge=True,
                )
            transaction.set(
                decision_ref,
                {
                    "decision_id": immutable_id,
                    "decision_subject_id": subject_id,
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "engine_version": decision.engine_version,
                    "is_current": True,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "payload": decision.model_dump(mode="json"),
                    "schema_version": "deal-decision/v2",
                },
            )
            transaction.set(
                current_ref,
                {
                    "decision_id": immutable_id,
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "engine_version": decision.engine_version,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )
            transaction.set(
                processing_ref,
                {
                    "decision_id": immutable_id,
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "engine_version": decision.engine_version,
                    "created_at": firestore.SERVER_TIMESTAMP,
                },
            )

        persist(transaction)

    def decision_exists(self, listing_id: str, content_hash: str, engine_version: str) -> bool:
        return (
            self.client.collection("decision_processing_keys")
            .document(_stable_id(listing_id, content_hash, engine_version))
            .get()
            .exists
        )

    def save_normalized_vehicle(self, vehicle: NormalizedVehicle) -> None:
        self.client.collection("normalized_vehicles").document(vehicle.listing_id).set(
            {
                "listing_id": vehicle.listing_id,
                "comparison_key": vehicle.comparison_key,
                "make_model": f"{vehicle.make}|{vehicle.model}",
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

    def comparable_vehicles(self, make: str, model: str) -> list[NormalizedVehicle]:
        """Читает из Firestore только одну марку и модель вместо всего рынка."""
        query = self.client.collection("normalized_vehicles").where(
            "make_model",
            "==",
            f"{make}|{model}",
        )
        results: list[NormalizedVehicle] = []
        for document in query.stream():
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
            reference = self.client.collection("normalized_vehicles").document(vehicle.listing_id)
            batch.set(
                reference,
                {
                    "listing_id": vehicle.listing_id,
                    "comparison_key": vehicle.comparison_key,
                    "make_model": f"{vehicle.make}|{vehicle.model}",
                    "updated_at": datetime.now(UTC),
                    "payload": vehicle.model_dump(mode="json"),
                },
            )
            operation_count += 1
            commit_if_needed()
        for identity in identities:
            reference = self.client.collection("vehicle_identities").document(identity.vehicle_id)
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
        decisions = [
            item
            for item in self.current_decisions(limit=10_000)
            if item[1].action in {DecisionAction.CONTACT, DecisionAction.INSPECT}
        ]
        return decisions[:limit]

    def current_decisions(self, limit: int = 100) -> list[tuple[ListingSnapshot, DealDecision]]:
        """Возвращает актуальные решения всех типов с соответствующими snapshots."""
        current = list(self.client.collection("current_decisions").stream())
        decision_refs = []
        for pointer in current:
            data = pointer.to_dict() or {}
            if data.get("decision_id"):
                decision_refs.append(
                    self.client.collection("decisions").document(str(data["decision_id"]))
                )
        documents = list(self.client.get_all(decision_refs))

        def created_at(document: firestore.DocumentSnapshot) -> datetime:
            data = document.to_dict() or {}
            value = data.get("created_at")
            return value if isinstance(value, datetime) else datetime.min.replace(tzinfo=UTC)

        documents.sort(key=created_at, reverse=True)
        ordered_decisions: list[tuple[str, DealDecision]] = []
        snapshot_references: dict[str, Any] = {}
        for document in documents:
            data = document.to_dict() or {}
            if "listing_id" not in data or "payload" not in data:
                continue
            decision = DealDecision.model_validate(data["payload"])
            snapshot_reference = (
                self.client.collection("listings")
                .document(data["listing_id"])
                .collection("snapshots")
                .document(data["content_hash"])
            )
            snapshot_references[snapshot_reference.path] = snapshot_reference
            ordered_decisions.append(
                (
                    snapshot_reference.path,
                    decision,
                )
            )
            if len(ordered_decisions) >= limit:
                break

        snapshots: dict[str, ListingSnapshot] = {}
        for snapshot in self.client.get_all(list(snapshot_references.values())):
            snapshot_data = snapshot.to_dict()
            if snapshot_data:
                snapshots[snapshot.reference.path] = ListingSnapshot.model_validate(
                    snapshot_data["payload"]
                )

        return [
            (snapshots[path], decision) for path, decision in ordered_decisions if path in snapshots
        ]

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

    def claim_telegram_update(
        self, update_id: int, lease_owner: str = "local", lease_seconds: int = 120
    ) -> bool:
        """Атомарно блокирует повторную обработку webhook-доставки Telegram."""
        reference = self.client.collection("telegram_updates").document(str(update_id))
        transaction = self.client.transaction()

        @firestore.transactional
        def claim(transaction: firestore.Transaction) -> bool:
            snapshot = reference.get(transaction=transaction)
            data = snapshot.to_dict() or {}
            now = datetime.now(UTC)
            if snapshot.exists:
                state = str(data.get("state", ProcessingState.COMPLETED.value))
                lease_expires_at = data.get("lease_expires_at")
                lease_active = isinstance(lease_expires_at, datetime) and lease_expires_at > now
                if state == ProcessingState.COMPLETED.value or (
                    state == ProcessingState.PROCESSING.value and lease_active
                ):
                    return False
            record = TelegramUpdateRecord(
                update_id=update_id,
                state=ProcessingState.PROCESSING,
                operation_id=canonical_hash(
                    "telegram-update-operation/v1", {"update_id": update_id}
                ),
                lease_owner=lease_owner,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            transaction.set(
                reference,
                {
                    "update_id": update_id,
                    "state": record.state.value,
                    "lease_expires_at": record.lease_expires_at,
                    "payload": record.model_dump(mode="json"),
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "schema_version": "telegram-update/v2",
                },
            )
            return True

        return cast(bool, claim(transaction))

    def finish_telegram_update(
        self, update_id: int, state: ProcessingState, error: str | None = None
    ) -> None:
        if state is ProcessingState.PROCESSING:
            raise ValueError("Финальное состояние Telegram update не может быть processing")
        reference = self.client.collection("telegram_updates").document(str(update_id))
        data = reference.get().to_dict()
        if not data or "payload" not in data:
            return
        record = TelegramUpdateRecord.model_validate(data["payload"])
        updated = record.model_copy(
            update={
                "state": state,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error": error,
                "updated_at": datetime.now(UTC),
            }
        )
        reference.set(
            {
                "state": state.value,
                "lease_expires_at": None,
                "payload": updated.model_dump(mode="json"),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        document = self.client.collection("user_settings").document(str(user_id)).get()
        data = document.to_dict()
        return UserSettings.model_validate(data) if data else None

    def save_user_settings(self, settings: UserSettings) -> None:
        self.client.collection("user_settings").document(str(settings.user_id)).set(
            settings.model_dump(mode="json")
        )

    def referral_summary(self) -> dict[str, int]:
        """Считает атрибуцию referral без раскрытия профилей пользователей."""
        summary: dict[str, int] = {}
        for document in self.client.collection("user_settings").stream():
            data = document.to_dict() or {}
            referrer = data.get("referred_by_user_id")
            if isinstance(referrer, int):
                key = str(referrer)
                summary[key] = summary.get(key, 0) + 1
        return summary

    def save_user_action(self, action: UserAction) -> None:
        document_id = _stable_id(str(action.user_id), action.listing_id)
        self.client.collection("user_actions").document(document_id).set(
            action.model_dump(mode="json")
        )

    def user_watchlist(self, user_id: int) -> list[str]:
        documents = (
            self.client.collection("user_actions")
            .where("user_id", "==", user_id)
            .where("action", "==", "WATCH")
            .stream()
        )
        return [str(data["listing_id"]) for document in documents if (data := document.to_dict())]

    def record_audit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Записывает append-only audit event с серверным временем."""
        reference = self.client.collection("audit_events").document()
        reference.set(
            {
                "event_type": event_type,
                "payload": payload,
                "created_at": firestore.SERVER_TIMESTAMP,
                "schema_version": "audit-event/v1",
            }
        )


def _stable_id(*parts: str) -> str:
    return canonical_hash("firestore-document-id/v1", {"parts": list(parts)})

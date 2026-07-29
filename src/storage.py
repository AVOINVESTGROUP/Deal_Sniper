"""Локальное хранилище MVP с версиями объявлений и решений."""

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from src.domain.ids import canonical_hash
from src.domain.models import (
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    NewsEvidence,
    NewsFeedConfiguration,
    NormalizedVehicle,
    OutboxRecord,
    OutboxState,
    Outcome,
    ProcessingState,
    PublicationEvent,
    RawSnapshotMetadata,
    SavedSearch,
    SourceConfiguration,
    TelegramUpdateRecord,
    UserAction,
    UserSettings,
    VehicleIdentity,
    VerificationEvidence,
)


class Repository(Protocol):
    """Контракт хранилища для локального и облачного режимов."""

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]: ...

    def save_snapshots(
        self,
        snapshots: list[ListingSnapshot],
    ) -> list[tuple[ListingSnapshot, bool, bool, str]]: ...

    def latest_snapshots(self) -> list[ListingSnapshot]: ...

    def snapshot_versions(self) -> list[ListingSnapshot]: ...

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None: ...

    def get_snapshot(self, listing_id: str, content_hash: str) -> ListingSnapshot | None: ...

    def is_current_snapshot(self, listing_id: str, content_hash: str) -> bool: ...

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None: ...

    def decision_exists(self, listing_id: str, content_hash: str, engine_version: str) -> bool: ...

    def save_normalized_vehicle(self, vehicle: NormalizedVehicle) -> None: ...

    def normalized_vehicles(self) -> list[NormalizedVehicle]: ...

    def comparable_vehicles(self, make: str, model: str) -> list[NormalizedVehicle]: ...

    def save_vehicle_identity(self, identity: VehicleIdentity) -> None: ...

    def save_normalized_market(
        self,
        vehicles: list[NormalizedVehicle],
        identities: list[VehicleIdentity],
    ) -> None: ...

    def save_raw_snapshot(self, metadata: RawSnapshotMetadata) -> None: ...

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]: ...

    def current_decisions(self, limit: int = 100) -> list[tuple[ListingSnapshot, DealDecision]]: ...

    def count_snapshots(self) -> int: ...

    def notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> bool: ...

    def mark_notification_sent(
        self, target_id: str, listing_id: str, content_hash: str
    ) -> None: ...

    def source_enabled(self, source_name: str, default: bool = True) -> bool: ...

    def set_source_enabled(self, source_name: str, enabled: bool) -> None: ...

    def list_source_configurations(self) -> list[SourceConfiguration]: ...

    def save_source_configuration(self, config: SourceConfiguration) -> None: ...

    def delete_source_configuration(self, source_name: str) -> bool: ...

    def list_news_feed_configurations(self) -> list[NewsFeedConfiguration]: ...

    def save_news_feed_configuration(self, config: NewsFeedConfiguration) -> None: ...

    def delete_news_feed_configuration(self, name: str) -> bool: ...

    def save_news_evidence(self, evidence: NewsEvidence) -> None: ...

    def get_news_evidence(self, evidence_id: str) -> NewsEvidence | None: ...

    def active_news_evidence(
        self, limit: int = 20, now: datetime | None = None
    ) -> list[NewsEvidence]: ...

    def record_source_run(self, source_name: str, payload: dict[str, Any]) -> None: ...

    def source_health(self) -> dict[str, dict[str, Any]]: ...

    def claim_telegram_update(
        self, update_id: int, lease_owner: str = "local", lease_seconds: int = 120
    ) -> bool: ...

    def finish_telegram_update(
        self, update_id: int, state: ProcessingState, error: str | None = None
    ) -> None: ...

    def get_user_settings(self, user_id: int) -> UserSettings | None: ...

    def save_user_settings(self, settings: UserSettings) -> None: ...

    def referral_summary(self) -> dict[str, int]: ...

    def save_user_action(self, action: UserAction) -> None: ...

    def user_watchlist(self, user_id: int) -> list[str]: ...

    def record_audit_event(self, event_type: str, payload: dict[str, Any]) -> None: ...

    def get_verification_evidence(self, verification_key: str) -> VerificationEvidence | None: ...

    def save_verification_evidence(self, evidence: VerificationEvidence) -> None: ...

    def put_outbox(self, record: OutboxRecord) -> OutboxRecord: ...

    def claim_outbox(
        self, delivery_id: str, lease_owner: str, lease_seconds: int = 120
    ) -> OutboxRecord | None: ...

    def update_outbox(
        self,
        delivery_id: str,
        state: OutboxState,
        *,
        error: str | None = None,
        telegram_message_id: str | None = None,
        provider_message_id: str | None = None,
    ) -> None: ...

    def get_outbox(self, delivery_id: str) -> OutboxRecord | None: ...

    def list_outbox(
        self, state: OutboxState | None = None, limit: int = 100
    ) -> list[OutboxRecord]: ...

    def reconcile_outbox(
        self, delivery_id: str, action: str, operation_id: str
    ) -> OutboxRecord | None: ...

    def save_search(self, search: SavedSearch) -> None: ...

    def user_searches(self, user_id: int) -> list[SavedSearch]: ...

    def active_searches(self) -> list[SavedSearch]: ...

    def set_search_enabled(self, user_id: int, search_id: str, enabled: bool) -> bool: ...

    def save_outcome(self, outcome: Outcome) -> None: ...

    def user_outcomes(self, user_id: int) -> list[Outcome]: ...

    def save_publication_event(self, event: PublicationEvent) -> None: ...

    def reserve_pro_cta_variant(self, publication_event_id: str, variant_count: int) -> int: ...

    def commit_publication_with_outbox(
        self, event: PublicationEvent, record: OutboxRecord
    ) -> OutboxRecord: ...

    def admin_summary(self) -> dict[str, Any]: ...

    def schema_version(self) -> str: ...

    def get_active_runtime_configuration(self) -> dict[str, Any] | None: ...

    def list_runtime_configurations(self, limit: int = 20) -> list[dict[str, Any]]: ...

    def activate_runtime_configuration(
        self, payload: dict[str, Any], operation_id: str
    ) -> dict[str, Any]: ...

    def runtime_configuration_for_operation(self, operation_id: str) -> dict[str, Any] | None: ...

    def claim_admin_operation(
        self, operation_id: str, operation: str, payload: dict[str, Any]
    ) -> bool: ...

    def complete_admin_operation(
        self, operation_id: str, state: str, result: dict[str, Any]
    ) -> None: ...

    def get_admin_operation(self, operation_id: str) -> dict[str, Any] | None: ...

    def list_admin_users(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]: ...


def snapshot_hash(snapshot: ListingSnapshot) -> str:
    """Вычисляет hash только по значимым полям объявления."""
    payload = snapshot.model_dump(
        mode="json",
        exclude={
            "observed_at",
            "source_observed_at",
            "fetched_at",
            "ingested_at",
            "version_sequence",
            "lifecycle",
            "correlation_id",
        },
    )
    return canonical_hash("listing-content/v2", payload)


class LocalRepository:
    """SQLite-реализация только для локального запуска и первого пилота."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    price_aed TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (listing_id, content_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_listing_time
                    ON snapshots(listing_id, observed_at DESC);
                CREATE TABLE IF NOT EXISTS listing_current (
                    listing_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    version_sequence INTEGER NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    tie_breaker TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (listing_id, content_hash)
                );
                CREATE TABLE IF NOT EXISTS decisions_v2 (
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (listing_id, content_hash, engine_version)
                );
                CREATE TABLE IF NOT EXISTS decisions_v3 (
                    decision_id TEXT PRIMARY KEY,
                    decision_subject_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decision_current (
                    decision_subject_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    target_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (target_id, listing_id, content_hash)
                );
                CREATE TABLE IF NOT EXISTS source_registry (
                    source_name TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS source_health (
                    source_name TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS source_configurations (
                    source_name TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS news_feed_configurations (
                    name TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS news_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    semantic_fingerprint TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    freshness_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_news_evidence_active
                    ON news_evidence(freshness_status, valid_until);
                CREATE TABLE IF NOT EXISTS telegram_updates (
                    update_id INTEGER PRIMARY KEY,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    state TEXT NOT NULL DEFAULT 'processing',
                    lease_expires_at TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS normalized_vehicles (
                    listing_id TEXT PRIMARY KEY,
                    comparison_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS vehicle_identities (
                    vehicle_id TEXT PRIMARY KEY,
                    comparison_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS raw_snapshots (
                    checksum_sha256 TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    storage_uri TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (checksum_sha256, source, source_url)
                );
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_actions (
                    user_id INTEGER NOT NULL,
                    listing_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, listing_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS verification_evidence (
                    verification_key TEXT PRIMARY KEY,
                    evidence_revision_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS delivery_outbox (
                    delivery_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    lease_expires_at TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS saved_searches (
                    search_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_saved_searches_owner
                    ON saved_searches(user_id, enabled);
                CREATE TABLE IF NOT EXISTS outcomes (
                    user_id INTEGER NOT NULL,
                    listing_id TEXT NOT NULL,
                    decision_content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, listing_id, decision_content_hash)
                );
                CREATE TABLE IF NOT EXISTS publication_events (
                    publication_event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS pro_cta_assignments (
                    assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    publication_event_id TEXT NOT NULL UNIQUE,
                    variant_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS runtime_configurations (
                    version TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS runtime_configuration_active (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_operations (
                    operation_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            telegram_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(telegram_updates)").fetchall()
            }
            if "state" not in telegram_columns:
                connection.execute(
                    "ALTER TABLE telegram_updates ADD COLUMN state TEXT NOT NULL "
                    "DEFAULT 'completed'"
                )
            if "lease_expires_at" not in telegram_columns:
                connection.execute("ALTER TABLE telegram_updates ADD COLUMN lease_expires_at TEXT")
            if "payload_json" not in telegram_columns:
                connection.execute("ALTER TABLE telegram_updates ADD COLUMN payload_json TEXT")
            listing_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(listing_current)").fetchall()
            }
            if "last_seen_at" not in listing_columns:
                connection.execute("ALTER TABLE listing_current ADD COLUMN last_seen_at TEXT")

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]:
        """Сохраняет новую версию и сообщает new/price_changed/hash."""
        listing_id = f"{snapshot.source}:{snapshot.source_listing_id}"
        content_hash = snapshot_hash(snapshot)
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT pointer.content_hash, pointer.version_sequence, snapshots.price_aed
                FROM listing_current AS pointer
                JOIN snapshots ON snapshots.listing_id = pointer.listing_id
                    AND snapshots.content_hash = pointer.content_hash
                WHERE pointer.listing_id = ?
                """,
                (listing_id,),
            ).fetchone()
            if current is not None and current["content_hash"] == content_hash:
                connection.execute(
                    "UPDATE listing_current SET last_seen_at = ? WHERE listing_id = ?",
                    (datetime.now(UTC).isoformat(), listing_id),
                )
                return False, False, content_hash
            sequence = snapshot.version_sequence
            if sequence is None:
                sequence = int(current["version_sequence"]) + 1 if current is not None else 1
            ingested_at = datetime.now(UTC)
            source_observed_at = snapshot.source_observed_at or snapshot.observed_at
            stored = snapshot.model_copy(
                update={"version_sequence": sequence, "ingested_at": ingested_at}
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO snapshots
                    (listing_id, content_hash, observed_at, price_aed, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    content_hash,
                    stored.observed_at.isoformat(),
                    str(snapshot.price_aed),
                    stored.model_dump_json(),
                ),
            )
            current_key = None
            if current is not None:
                pointer = connection.execute(
                    "SELECT * FROM listing_current WHERE listing_id = ?", (listing_id,)
                ).fetchone()
                current_key = (
                    int(pointer["version_sequence"]),
                    str(pointer["source_observed_at"]),
                    str(pointer["fetched_at"]),
                    str(pointer["tie_breaker"]),
                )
            candidate_key = (
                sequence,
                source_observed_at.isoformat(),
                stored.fetched_at.isoformat(),
                content_hash,
            )
            if current_key is None or candidate_key > current_key:
                connection.execute(
                    """
                    INSERT INTO listing_current(
                        listing_id, content_hash, version_sequence, source_observed_at,
                        fetched_at, ingested_at, tie_breaker, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(listing_id) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        version_sequence = excluded.version_sequence,
                        source_observed_at = excluded.source_observed_at,
                        fetched_at = excluded.fetched_at,
                        ingested_at = excluded.ingested_at,
                        tie_breaker = excluded.tie_breaker,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        listing_id,
                        content_hash,
                        sequence,
                        source_observed_at.isoformat(),
                        stored.fetched_at.isoformat(),
                        ingested_at.isoformat(),
                        content_hash,
                        ingested_at.isoformat(),
                    ),
                )
        price_changed = current is not None and current["price_aed"] != str(snapshot.price_aed)
        return current is None, price_changed, content_hash

    def save_snapshots(
        self,
        snapshots: list[ListingSnapshot],
    ) -> list[tuple[ListingSnapshot, bool, bool, str]]:
        """Локально сохраняет пакет через существующую транзакционную операцию."""
        return [(snapshot, *self.save_snapshot(snapshot)) for snapshot in snapshots]

    def latest_snapshots(self) -> list[ListingSnapshot]:
        """Возвращает последнюю версию каждого объявления."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshots.payload_json
                FROM listing_current
                JOIN snapshots ON snapshots.listing_id = listing_current.listing_id
                    AND snapshots.content_hash = listing_current.content_hash
                """
            ).fetchall()
        return [ListingSnapshot.model_validate_json(row["payload_json"]) for row in rows]

    def snapshot_versions(self) -> list[ListingSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM snapshots ORDER BY observed_at DESC"
            ).fetchall()
        return [ListingSnapshot.model_validate_json(row["payload_json"]) for row in rows]

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT snapshots.payload_json
                FROM listing_current
                JOIN snapshots ON snapshots.listing_id = listing_current.listing_id
                    AND snapshots.content_hash = listing_current.content_hash
                WHERE listing_current.listing_id = ?
                """,
                (listing_id,),
            ).fetchone()
        return ListingSnapshot.model_validate_json(row["payload_json"]) if row else None

    def get_snapshot(self, listing_id: str, content_hash: str) -> ListingSnapshot | None:
        """Возвращает только точную неизменяемую версию объявления."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM snapshots
                WHERE listing_id = ? AND content_hash = ?
                """,
                (listing_id, content_hash),
            ).fetchone()
        return ListingSnapshot.model_validate_json(row["payload_json"]) if row else None

    def is_current_snapshot(self, listing_id: str, content_hash: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content_hash FROM listing_current WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
        return bool(row and row["content_hash"] == content_hash)

    def get_verification_evidence(self, verification_key: str) -> VerificationEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM verification_evidence WHERE verification_key = ?",
                (verification_key,),
            ).fetchone()
        return VerificationEvidence.model_validate_json(row["payload_json"]) if row else None

    def save_verification_evidence(self, evidence: VerificationEvidence) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO verification_evidence(
                    verification_key, evidence_revision_id, status, valid_until, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(verification_key) DO UPDATE SET
                    evidence_revision_id = excluded.evidence_revision_id,
                    status = excluded.status,
                    valid_until = excluded.valid_until,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    evidence.verification_key,
                    evidence.evidence_revision_id,
                    evidence.status.value,
                    evidence.valid_until.isoformat(),
                    evidence.model_dump_json(),
                ),
            )

    def put_outbox(self, record: OutboxRecord) -> OutboxRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO delivery_outbox(delivery_id, state, payload_json)
                VALUES (?, ?, ?)
                """,
                (record.delivery_id, record.state.value, record.model_dump_json()),
            )
            row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (record.delivery_id,),
            ).fetchone()
        return OutboxRecord.model_validate_json(row["payload_json"])

    def claim_outbox(
        self, delivery_id: str, lease_owner: str, lease_seconds: int = 120
    ) -> OutboxRecord | None:
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                return None
            record = OutboxRecord.model_validate_json(row["payload_json"])
            leased = record.lease_expires_at is not None and record.lease_expires_at > now
            if record.state in {OutboxState.SENT, OutboxState.UNKNOWN} or (
                record.state is OutboxState.SENDING and leased
            ):
                return None
            lease_until = now + timedelta(seconds=lease_seconds)
            claimed = record.model_copy(
                update={
                    "state": OutboxState.SENDING,
                    "attempt_id": f"{delivery_id}:{int(now.timestamp() * 1000)}",
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_until,
                    "last_attempt_at": now,
                    "updated_at": now,
                }
            )
            connection.execute(
                """
                UPDATE delivery_outbox
                SET state = ?, lease_expires_at = ?, payload_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE delivery_id = ?
                """,
                (
                    claimed.state.value,
                    lease_until.isoformat(),
                    claimed.model_dump_json(),
                    delivery_id,
                ),
            )
        return claimed

    def update_outbox(
        self,
        delivery_id: str,
        state: OutboxState,
        *,
        error: str | None = None,
        telegram_message_id: str | None = None,
        provider_message_id: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                return
            record = OutboxRecord.model_validate_json(row["payload_json"])
            updated = record.model_copy(
                update={
                    "state": state,
                    "last_error": error,
                    "telegram_message_id": telegram_message_id,
                    "provider_message_id": provider_message_id or telegram_message_id,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            )
            connection.execute(
                """
                UPDATE delivery_outbox
                SET state = ?, lease_expires_at = NULL, payload_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE delivery_id = ?
                """,
                (state.value, updated.model_dump_json(), delivery_id),
            )

    def get_outbox(self, delivery_id: str) -> OutboxRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
        return OutboxRecord.model_validate_json(row["payload_json"]) if row else None

    def list_outbox(self, state: OutboxState | None = None, limit: int = 100) -> list[OutboxRecord]:
        with self._connect() as connection:
            if state is None:
                rows = connection.execute(
                    "SELECT payload_json FROM delivery_outbox ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload_json FROM delivery_outbox
                    WHERE state = ? ORDER BY updated_at DESC LIMIT ?
                    """,
                    (state.value, limit),
                ).fetchall()
        return [OutboxRecord.model_validate_json(row["payload_json"]) for row in rows]

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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                return None
            record = OutboxRecord.model_validate_json(row["payload_json"])
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
            connection.execute(
                """
                UPDATE delivery_outbox SET state = ?, payload_json = ?,
                    updated_at = CURRENT_TIMESTAMP WHERE delivery_id = ?
                """,
                (target_state.value, updated.model_dump_json(), delivery_id),
            )
            connection.execute(
                "INSERT INTO audit_events(event_type, payload_json) VALUES (?, ?)",
                ("outbox_reconciliation", json.dumps(event, ensure_ascii=False)),
            )
        return updated

    def save_search(self, search: SavedSearch) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO saved_searches(search_id, user_id, enabled, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    search.search_id,
                    search.user_id,
                    int(search.enabled),
                    search.model_dump_json(),
                ),
            )

    def user_searches(self, user_id: int) -> list[SavedSearch]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM saved_searches WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [SavedSearch.model_validate_json(row["payload_json"]) for row in rows]

    def active_searches(self) -> list[SavedSearch]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM saved_searches WHERE enabled = 1"
            ).fetchall()
        return [SavedSearch.model_validate_json(row["payload_json"]) for row in rows]

    def set_search_enabled(self, user_id: int, search_id: str, enabled: bool) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM saved_searches
                WHERE user_id = ? AND search_id = ?
                """,
                (user_id, search_id),
            ).fetchone()
            if row is None:
                return False
            search = SavedSearch.model_validate_json(row["payload_json"])
            updated = search.model_copy(update={"enabled": enabled})
            connection.execute(
                """
                UPDATE saved_searches SET enabled = ?, payload_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND search_id = ?
                """,
                (int(enabled), updated.model_dump_json(), user_id, search_id),
            )
        return True

    def save_outcome(self, outcome: Outcome) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outcomes(user_id, listing_id, decision_content_hash, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, listing_id, decision_content_hash) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    outcome.user_id,
                    outcome.listing_id,
                    outcome.decision_content_hash,
                    outcome.model_dump_json(),
                ),
            )

    def user_outcomes(self, user_id: int) -> list[Outcome]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM outcomes WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [Outcome.model_validate_json(row["payload_json"]) for row in rows]

    def save_publication_event(self, event: PublicationEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO publication_events(publication_event_id, payload_json)
                VALUES (?, ?)
                """,
                (event.publication_event_id, event.model_dump_json()),
            )

    def commit_publication_with_outbox(
        self, event: PublicationEvent, record: OutboxRecord
    ) -> OutboxRecord:
        """Атомарно фиксирует immutable publication revision и её outbox."""
        if record.payload.get("publication_event_id") != event.publication_event_id:
            raise ValueError("Outbox ссылается на другую publication revision")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            event_row = connection.execute(
                "SELECT payload_json FROM publication_events WHERE publication_event_id = ?",
                (event.publication_event_id,),
            ).fetchone()
            outbox_row = connection.execute(
                "SELECT payload_json FROM delivery_outbox WHERE delivery_id = ?",
                (record.delivery_id,),
            ).fetchone()
            if (event_row is None) != (outbox_row is None):
                raise RuntimeError("Нарушена атомарность publication revision и outbox")
            if event_row is not None and outbox_row is not None:
                stored_event = PublicationEvent.model_validate_json(event_row["payload_json"])
                stored_record = OutboxRecord.model_validate_json(outbox_row["payload_json"])
                if (
                    stored_event.model_dump(exclude={"created_at"})
                    != event.model_dump(exclude={"created_at"})
                    or stored_record.model_dump(
                        exclude={"state", "attempts", "created_at", "updated_at"}
                    )
                    != record.model_dump(
                        exclude={"state", "attempts", "created_at", "updated_at"}
                    )
                    or stored_record.payload != record.payload
                ):
                    raise RuntimeError("Retry изменил immutable publication payload")
                return stored_record
            connection.execute(
                """
                INSERT INTO publication_events(publication_event_id, payload_json)
                VALUES (?, ?)
                """,
                (event.publication_event_id, event.model_dump_json()),
            )
            connection.execute(
                """
                INSERT INTO delivery_outbox(delivery_id, state, payload_json)
                VALUES (?, ?, ?)
                """,
                (record.delivery_id, record.state.value, record.model_dump_json()),
            )
            return record

    def reserve_pro_cta_variant(self, publication_event_id: str, variant_count: int) -> int:
        """Атомарно назначает следующий CTA, сохраняя выбор для повторной задачи."""
        if variant_count < 1:
            raise ValueError("Пул CTA не может быть пустым")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT variant_index FROM pro_cta_assignments WHERE publication_event_id = ?",
                (publication_event_id,),
            ).fetchone()
            if existing is not None:
                return int(existing["variant_index"])
            latest = connection.execute(
                "SELECT variant_index FROM pro_cta_assignments ORDER BY assignment_id DESC LIMIT 1"
            ).fetchone()
            variant_index = (int(latest["variant_index"]) + 1) % variant_count if latest else 0
            connection.execute(
                """
                INSERT INTO pro_cta_assignments(publication_event_id, variant_index)
                VALUES (?, ?)
                """,
                (publication_event_id, variant_index),
            )
            return variant_index

    def admin_summary(self) -> dict[str, Any]:
        tables = {
            "users": "user_settings",
            "searches": "saved_searches",
            "outbox": "delivery_outbox",
            "audit_events": "audit_events",
            "quarantine": "verification_evidence",
            "current_decisions": "decision_current",
            "outcomes": "outcomes",
        }
        with self._connect() as connection:
            counts = {
                name: int(
                    connection.execute(f"SELECT COUNT(*) AS amount FROM {table}").fetchone()[
                        "amount"
                    ]
                )
                for name, table in tables.items()
            }
            outbox_states = {
                row["state"]: int(row["amount"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS amount FROM delivery_outbox GROUP BY state"
                ).fetchall()
            }
        return {"counts": counts, "outbox_states": outbox_states}

    def schema_version(self) -> str:
        return "2"

    def get_active_runtime_configuration(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT revision.payload_json
                FROM runtime_configuration_active AS active
                JOIN runtime_configurations AS revision ON revision.version = active.version
                WHERE active.singleton = 1
                """
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_runtime_configurations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM runtime_configurations ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def activate_runtime_configuration(
        self, payload: dict[str, Any], operation_id: str
    ) -> dict[str, Any]:
        version = str(payload["version"])
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            repeated = connection.execute(
                "SELECT payload_json FROM runtime_configurations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if repeated:
                return cast(dict[str, Any], json.loads(repeated["payload_json"]))
            active = connection.execute(
                "SELECT version FROM runtime_configuration_active WHERE singleton = 1"
            ).fetchone()
            previous_version = str(active["version"]) if active else None
            if previous_version:
                previous = connection.execute(
                    "SELECT payload_json FROM runtime_configurations WHERE version = ?",
                    (previous_version,),
                ).fetchone()
                if previous:
                    previous_payload = json.loads(previous["payload_json"])
                    previous_payload["state"] = "archived"
                    connection.execute(
                        "UPDATE runtime_configurations SET state = 'archived', "
                        "payload_json = ? WHERE version = ?",
                        (json.dumps(previous_payload, ensure_ascii=False), previous_version),
                    )
            stored = {**payload, "state": "active", "previous_version": previous_version}
            connection.execute(
                "INSERT INTO runtime_configurations"
                "(version, state, operation_id, payload_json) "
                "VALUES (?, 'active', ?, ?)",
                (version, operation_id, json.dumps(stored, ensure_ascii=False)),
            )
            connection.execute(
                "INSERT INTO runtime_configuration_active(singleton, version) VALUES (1, ?) "
                "ON CONFLICT(singleton) DO UPDATE SET version = excluded.version",
                (version,),
            )
            connection.execute(
                "INSERT INTO audit_events(event_type, payload_json) VALUES (?, ?)",
                (
                    "runtime_configuration_activated",
                    json.dumps(
                        {
                            "operation_id": operation_id,
                            "version": version,
                            "previous_version": previous_version,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
        return stored

    def runtime_configuration_for_operation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_configurations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        return cast(dict[str, Any], json.loads(row["payload_json"])) if row else None

    def claim_admin_operation(
        self, operation_id: str, operation: str, payload: dict[str, Any]
    ) -> bool:
        """Атомарно резервирует идентификатор административной операции."""
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO admin_operations"
                "(operation_id, operation, state, payload_json) VALUES (?, ?, 'running', ?)",
                (operation_id, operation, json.dumps(payload, ensure_ascii=False)),
            )
        return cursor.rowcount == 1

    def complete_admin_operation(
        self, operation_id: str, state: str, result: dict[str, Any]
    ) -> None:
        if state not in {"completed", "failed"}:
            raise ValueError("Недопустимое состояние административной операции")
        with self._connect() as connection:
            connection.execute(
                "UPDATE admin_operations SET state = ?, result_json = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE operation_id = ?",
                (state, json.dumps(result, ensure_ascii=False), operation_id),
            )

    def get_admin_operation(self, operation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT operation_id, operation, state, payload_json, result_json "
                "FROM admin_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "operation_id": row["operation_id"],
            "operation": row["operation"],
            "state": row["state"],
            "payload": json.loads(row["payload_json"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }

    def list_admin_users(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, payload_json, updated_at FROM user_settings "
                "ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "user_id": int(row["user_id"]),
                "settings": json.loads(row["payload_json"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_type, payload_json, created_at FROM audit_events "
                "ORDER BY event_id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        """Идемпотентно сохраняет решение для конкретной версии."""
        with self._connect() as connection:
            current_decision_id = decision.decision_id or canonical_hash(
                "legacy-decision-pointer/v1",
                {
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "engine_version": decision.engine_version,
                },
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions_v3(
                    decision_id, decision_subject_id, listing_id, content_hash,
                    engine_version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    current_decision_id,
                    decision.decision_subject_id or listing_id,
                    listing_id,
                    content_hash,
                    decision.engine_version,
                    decision.model_dump_json(),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions_v2
                    (listing_id, content_hash, engine_version, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    listing_id,
                    content_hash,
                    decision.engine_version,
                    decision.model_dump_json(),
                ),
            )
            connection.execute(
                """
                    INSERT INTO decision_current(
                        decision_subject_id, decision_id, listing_id,
                        content_hash, engine_version
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(decision_subject_id) DO UPDATE SET
                        decision_id = excluded.decision_id,
                        listing_id = excluded.listing_id,
                        content_hash = excluded.content_hash,
                        engine_version = excluded.engine_version,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                (
                    decision.decision_subject_id or listing_id,
                    current_decision_id,
                    listing_id,
                    content_hash,
                    decision.engine_version,
                ),
            )

    def decision_exists(self, listing_id: str, content_hash: str, engine_version: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM decisions_v2
                WHERE listing_id = ? AND content_hash = ? AND engine_version = ?
                """,
                (listing_id, content_hash, engine_version),
            ).fetchone()
        return row is not None

    def save_normalized_vehicle(self, vehicle: NormalizedVehicle) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO normalized_vehicles(listing_id, comparison_key, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(listing_id) DO UPDATE SET
                    comparison_key = excluded.comparison_key,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (vehicle.listing_id, vehicle.comparison_key, vehicle.model_dump_json()),
            )

    def normalized_vehicles(self) -> list[NormalizedVehicle]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM normalized_vehicles").fetchall()
        return [NormalizedVehicle.model_validate_json(row["payload_json"]) for row in rows]

    def comparable_vehicles(self, make: str, model: str) -> list[NormalizedVehicle]:
        """Возвращает ограниченный набор одной марки и модели для расчёта аналогов."""
        return [
            vehicle
            for vehicle in self.normalized_vehicles()
            if vehicle.make == make and vehicle.model == model
        ]

    def save_vehicle_identity(self, identity: VehicleIdentity) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicle_identities(vehicle_id, comparison_key, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(vehicle_id) DO UPDATE SET
                    comparison_key = excluded.comparison_key,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (identity.vehicle_id, identity.comparison_key, identity.model_dump_json()),
            )

    def save_normalized_market(
        self,
        vehicles: list[NormalizedVehicle],
        identities: list[VehicleIdentity],
    ) -> None:
        for vehicle in vehicles:
            self.save_normalized_vehicle(vehicle)
        for identity in identities:
            self.save_vehicle_identity(identity)

    def save_raw_snapshot(self, metadata: RawSnapshotMetadata) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO raw_snapshots(
                    checksum_sha256, source, source_url, storage_uri,
                    content_type, size_bytes, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.checksum_sha256,
                    metadata.source,
                    str(metadata.source_url),
                    metadata.storage_uri,
                    metadata.content_type,
                    metadata.size_bytes,
                    metadata.fetched_at.isoformat(),
                ),
            )

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]:
        """Возвращает последние рассчитанные карточки."""
        decisions = [
            item
            for item in self.current_decisions(limit=10_000)
            if item[1].action in {DecisionAction.CONTACT, DecisionAction.INSPECT}
        ]
        return decisions[:limit]

    def current_decisions(self, limit: int = 100) -> list[tuple[ListingSnapshot, DealDecision]]:
        """Возвращает актуальные решения всех типов для обзора рынка."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.payload_json AS listing_json, d.payload_json AS decision_json
                FROM decisions_v3 d
                JOIN decision_current c
                  ON c.decision_id = d.decision_id
                JOIN snapshots s
                  ON s.listing_id = d.listing_id AND s.content_hash = d.content_hash
                ORDER BY d.created_at DESC
                """,
            ).fetchall()
        decisions: list[tuple[ListingSnapshot, DealDecision]] = []
        for row in rows:
            decision = DealDecision.model_validate_json(row["decision_json"])
            decisions.append((ListingSnapshot.model_validate_json(row["listing_json"]), decision))
            if len(decisions) >= limit:
                break
        return decisions

    def count_snapshots(self) -> int:
        """Количество сохранённых версий для статуса бота."""
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS amount FROM snapshots").fetchone()
        return int(row["amount"] if row else 0)

    def notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> bool:
        """Проверяет, отправлялась ли конкретная версия в заданный канал."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM notifications
                WHERE target_id = ? AND listing_id = ? AND content_hash = ?
                """,
                (target_id, listing_id, content_hash),
            ).fetchone()
        return row is not None

    def mark_notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> None:
        """Идемпотентно отмечает успешную Telegram-доставку."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO notifications(target_id, listing_id, content_hash)
                VALUES (?, ?, ?)
                """,
                (target_id, listing_id, content_hash),
            )

    def source_enabled(self, source_name: str, default: bool = True) -> bool:
        """Возвращает сохранённое состояние источника или его состояние по умолчанию."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT enabled FROM source_registry WHERE source_name = ?",
                (source_name,),
            ).fetchone()
        return bool(row["enabled"]) if row is not None else default

    def set_source_enabled(self, source_name: str, enabled: bool) -> None:
        """Включает или отключает источник без удаления накопленной истории."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_registry(source_name, enabled, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source_name, int(enabled)),
            )

    def list_source_configurations(self) -> list[SourceConfiguration]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM source_configurations ORDER BY source_name"
            ).fetchall()
        return [SourceConfiguration.model_validate_json(row["payload_json"]) for row in rows]

    def save_source_configuration(self, config: SourceConfiguration) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_configurations(source_name, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_name) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (config.name, config.model_dump_json()),
            )
            connection.execute(
                """
                INSERT INTO source_registry(source_name, enabled, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (config.name, int(config.enabled)),
            )

    def delete_source_configuration(self, source_name: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM source_configurations WHERE source_name = ?", (source_name,)
            )
            connection.execute("DELETE FROM source_registry WHERE source_name = ?", (source_name,))
        return cursor.rowcount > 0

    def list_news_feed_configurations(self) -> list[NewsFeedConfiguration]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM news_feed_configurations ORDER BY name"
            ).fetchall()
        return [NewsFeedConfiguration.model_validate_json(row["payload_json"]) for row in rows]

    def save_news_feed_configuration(self, config: NewsFeedConfiguration) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO news_feed_configurations(name, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (config.name, config.model_dump_json()),
            )

    def delete_news_feed_configuration(self, name: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM news_feed_configurations WHERE name = ?", (name,)
            )
        return cursor.rowcount > 0

    def save_news_evidence(self, evidence: NewsEvidence) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO news_evidence(
                    evidence_id, semantic_fingerprint, valid_until,
                    freshness_status, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    valid_until = excluded.valid_until,
                    freshness_status = excluded.freshness_status,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    evidence.evidence_id,
                    evidence.semantic_fingerprint,
                    evidence.valid_until.isoformat(),
                    evidence.freshness_status.value,
                    evidence.model_dump_json(),
                ),
            )

    def get_news_evidence(self, evidence_id: str) -> NewsEvidence | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM news_evidence WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        return NewsEvidence.model_validate_json(row["payload_json"]) if row else None

    def active_news_evidence(
        self, limit: int = 20, now: datetime | None = None
    ) -> list[NewsEvidence]:
        current = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM news_evidence
                WHERE freshness_status = ? AND valid_until > ?
                ORDER BY valid_until DESC LIMIT ?
                """,
                ("active", current, max(1, limit)),
            ).fetchall()
        evidence = [NewsEvidence.model_validate_json(row["payload_json"]) for row in rows]
        return sorted(evidence, key=lambda item: item.published_at, reverse=True)

    def record_source_run(self, source_name: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_health(source_name, payload_json) VALUES (?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    payload_json = excluded.payload_json, updated_at = CURRENT_TIMESTAMP
                """,
                (source_name, json.dumps(payload, ensure_ascii=False)),
            )

    def source_health(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source_name, payload_json FROM source_health"
            ).fetchall()
        return {str(row["source_name"]): json.loads(row["payload_json"]) for row in rows}

    def claim_telegram_update(
        self, update_id: int, lease_owner: str = "local", lease_seconds: int = 120
    ) -> bool:
        """Атомарно закрепляет Telegram update за единственным обработчиком."""
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state, lease_expires_at FROM telegram_updates WHERE update_id = ?",
                (update_id,),
            ).fetchone()
            if row is not None:
                lease_value = row["lease_expires_at"]
                lease_active = bool(lease_value and datetime.fromisoformat(str(lease_value)) > now)
                if row["state"] == ProcessingState.COMPLETED.value or (
                    row["state"] == ProcessingState.PROCESSING.value and lease_active
                ):
                    return False
            record = TelegramUpdateRecord(
                update_id=update_id,
                state=ProcessingState.PROCESSING,
                operation_id=canonical_hash(
                    "telegram-update-operation/v1", {"update_id": update_id}
                ),
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
            )
            connection.execute(
                """
                INSERT INTO telegram_updates(update_id, state, lease_expires_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(update_id) DO UPDATE SET
                    state = excluded.state,
                    lease_expires_at = excluded.lease_expires_at,
                    payload_json = excluded.payload_json,
                    claimed_at = CURRENT_TIMESTAMP
                """,
                (
                    update_id,
                    record.state.value,
                    lease_expires_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
        return True

    def finish_telegram_update(
        self, update_id: int, state: ProcessingState, error: str | None = None
    ) -> None:
        if state is ProcessingState.PROCESSING:
            raise ValueError("Финальное состояние Telegram update не может быть processing")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM telegram_updates WHERE update_id = ?", (update_id,)
            ).fetchone()
            if row is None or not row["payload_json"]:
                return
            record = TelegramUpdateRecord.model_validate_json(row["payload_json"])
            updated = record.model_copy(
                update={
                    "state": state,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error": error,
                    "updated_at": datetime.now(UTC),
                }
            )
            connection.execute(
                """
                UPDATE telegram_updates SET state = ?, lease_expires_at = NULL,
                    payload_json = ? WHERE update_id = ?
                """,
                (state.value, updated.model_dump_json(), update_id),
            )

    def get_user_settings(self, user_id: int) -> UserSettings | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM user_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        return UserSettings.model_validate_json(row["payload_json"]) if row else None

    def save_user_settings(self, settings: UserSettings) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_settings(user_id, payload_json) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (settings.user_id, settings.model_dump_json()),
            )

    def referral_summary(self) -> dict[str, int]:
        """Считает атрибутированных пользователей по referrer ID."""
        with self._connect() as connection:
            rows = connection.execute("SELECT payload_json FROM user_settings").fetchall()
        summary: dict[str, int] = {}
        for row in rows:
            settings = UserSettings.model_validate_json(row["payload_json"])
            if settings.referred_by_user_id is not None:
                key = str(settings.referred_by_user_id)
                summary[key] = summary.get(key, 0) + 1
        return summary

    def save_user_action(self, action: UserAction) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_actions(user_id, listing_id, action, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, listing_id) DO UPDATE SET
                    action = excluded.action, payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (action.user_id, action.listing_id, action.action, action.model_dump_json()),
            )

    def user_watchlist(self, user_id: int) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT listing_id FROM user_actions
                WHERE user_id = ? AND action = 'WATCH' ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [str(row["listing_id"]) for row in rows]

    def record_audit_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Записывает безопасный локальный audit trail."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(event_type, payload_json) VALUES (?, ?)",
                (event_type, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def import_snapshots(self, snapshots: Iterable[ListingSnapshot]) -> int:
        """Упрощает тестовую пакетную загрузку без mock fallback."""
        return sum(1 for item in snapshots if self.save_snapshot(item)[0])

"""Локальное хранилище MVP с версиями объявлений и решений."""

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from src.domain.models import (
    DealDecision,
    ListingSnapshot,
    NormalizedVehicle,
    RawSnapshotMetadata,
    UserAction,
    UserSettings,
    VehicleIdentity,
)


class Repository(Protocol):
    """Контракт хранилища для локального и облачного режимов."""

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]: ...

    def latest_snapshots(self) -> list[ListingSnapshot]: ...

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None: ...

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None: ...

    def decision_exists(
        self, listing_id: str, content_hash: str, engine_version: str
    ) -> bool: ...

    def save_normalized_vehicle(self, vehicle: NormalizedVehicle) -> None: ...

    def normalized_vehicles(self) -> list[NormalizedVehicle]: ...

    def save_vehicle_identity(self, identity: VehicleIdentity) -> None: ...

    def save_normalized_market(
        self,
        vehicles: list[NormalizedVehicle],
        identities: list[VehicleIdentity],
    ) -> None: ...

    def save_raw_snapshot(self, metadata: RawSnapshotMetadata) -> None: ...

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]: ...

    def count_snapshots(self) -> int: ...

    def notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> bool: ...

    def mark_notification_sent(
        self, target_id: str, listing_id: str, content_hash: str
    ) -> None: ...

    def source_enabled(self, source_name: str, default: bool = True) -> bool: ...

    def set_source_enabled(self, source_name: str, enabled: bool) -> None: ...

    def record_source_run(self, source_name: str, payload: dict[str, Any]) -> None: ...

    def source_health(self) -> dict[str, dict[str, Any]]: ...

    def claim_telegram_update(self, update_id: int) -> bool: ...

    def get_user_settings(self, user_id: int) -> UserSettings | None: ...

    def save_user_settings(self, settings: UserSettings) -> None: ...

    def save_user_action(self, action: UserAction) -> None: ...

    def user_watchlist(self, user_id: int) -> list[str]: ...


def snapshot_hash(snapshot: ListingSnapshot) -> str:
    """Вычисляет hash только по значимым полям объявления."""
    payload = snapshot.model_dump(
        mode="json",
        exclude={"observed_at"},
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class LocalRepository:
    """SQLite-реализация только для локального запуска и первого пилота."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

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
                CREATE TABLE IF NOT EXISTS telegram_updates (
                    update_id INTEGER PRIMARY KEY,
                    claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
                """
            )

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]:
        """Сохраняет новую версию и сообщает new/price_changed/hash."""
        listing_id = f"{snapshot.source}:{snapshot.source_listing_id}"
        content_hash = snapshot_hash(snapshot)
        with self._connect() as connection:
            previous = connection.execute(
                """
                SELECT price_aed, content_hash FROM snapshots
                WHERE listing_id = ? ORDER BY observed_at DESC LIMIT 1
                """,
                (listing_id,),
            ).fetchone()
            if previous is not None and previous["content_hash"] == content_hash:
                return False, False, content_hash
            connection.execute(
                """
                INSERT OR IGNORE INTO snapshots
                    (listing_id, content_hash, observed_at, price_aed, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    listing_id,
                    content_hash,
                    snapshot.observed_at.isoformat(),
                    str(snapshot.price_aed),
                    snapshot.model_dump_json(),
                ),
            )
        price_changed = previous is not None and previous["price_aed"] != str(snapshot.price_aed)
        return previous is None, price_changed, content_hash

    def latest_snapshots(self) -> list[ListingSnapshot]:
        """Возвращает последнюю версию каждого объявления."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM snapshots AS current
                WHERE observed_at = (
                    SELECT MAX(observed_at) FROM snapshots AS candidate
                    WHERE candidate.listing_id = current.listing_id
                )
                """
            ).fetchall()
        return [ListingSnapshot.model_validate_json(row["payload_json"]) for row in rows]

    def latest_snapshot(self, listing_id: str) -> ListingSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM snapshots
                WHERE listing_id = ? ORDER BY observed_at DESC LIMIT 1
                """,
                (listing_id,),
            ).fetchone()
        return ListingSnapshot.model_validate_json(row["payload_json"]) if row else None

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        """Идемпотентно сохраняет решение для конкретной версии."""
        with self._connect() as connection:
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

    def decision_exists(
        self, listing_id: str, content_hash: str, engine_version: str
    ) -> bool:
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
            rows = connection.execute(
                "SELECT payload_json FROM normalized_vehicles"
            ).fetchall()
        return [NormalizedVehicle.model_validate_json(row["payload_json"]) for row in rows]

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
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.payload_json AS listing_json, d.payload_json AS decision_json
                FROM decisions_v2 d
                JOIN snapshots s
                  ON s.listing_id = d.listing_id AND s.content_hash = d.content_hash
                ORDER BY d.created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            (
                ListingSnapshot.model_validate_json(row["listing_json"]),
                DealDecision.model_validate_json(row["decision_json"]),
            )
            for row in rows
        ]

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

    def claim_telegram_update(self, update_id: int) -> bool:
        """Атомарно закрепляет Telegram update за единственным обработчиком."""
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO telegram_updates(update_id) VALUES (?)",
                (update_id,),
            )
        return cursor.rowcount == 1

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

    def import_snapshots(self, snapshots: Iterable[ListingSnapshot]) -> int:
        """Упрощает тестовую пакетную загрузку без mock fallback."""
        return sum(1 for item in snapshots if self.save_snapshot(item)[0])

"""Локальное хранилище MVP с версиями объявлений и решений."""

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from src.domain.models import DealDecision, ListingSnapshot


class Repository(Protocol):
    """Контракт хранилища для локального и облачного режимов."""

    def save_snapshot(self, snapshot: ListingSnapshot) -> tuple[bool, bool, str]: ...

    def latest_snapshots(self) -> list[ListingSnapshot]: ...

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None: ...

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]: ...

    def count_snapshots(self) -> int: ...

    def notification_sent(self, target_id: str, listing_id: str, content_hash: str) -> bool: ...

    def mark_notification_sent(
        self, target_id: str, listing_id: str, content_hash: str
    ) -> None: ...


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
                CREATE TABLE IF NOT EXISTS notifications (
                    target_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (target_id, listing_id, content_hash)
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

    def save_decision(self, listing_id: str, content_hash: str, decision: DealDecision) -> None:
        """Идемпотентно сохраняет решение для конкретной версии."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO decisions(listing_id, content_hash, payload_json)
                VALUES (?, ?, ?)
                """,
                (listing_id, content_hash, decision.model_dump_json()),
            )

    def latest_decisions(self, limit: int = 10) -> list[tuple[ListingSnapshot, DealDecision]]:
        """Возвращает последние рассчитанные карточки."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.payload_json AS listing_json, d.payload_json AS decision_json
                FROM decisions d
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

    def import_snapshots(self, snapshots: Iterable[ListingSnapshot]) -> int:
        """Упрощает тестовую пакетную загрузку без mock fallback."""
        return sum(1 for item in snapshots if self.save_snapshot(item)[0])

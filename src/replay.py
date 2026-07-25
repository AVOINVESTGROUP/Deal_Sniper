"""Catch-up текущих snapshots после миграции без включения delivery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from google.cloud import firestore

from src.config import Settings
from src.service import DealService
from src.tasks import CloudTaskDispatcher


@dataclass(frozen=True, slots=True)
class ReplayReport:
    pending: int
    enqueued: int
    skipped: int
    completed: int = 0
    failed: int = 0


async def enqueue_migration_replay(settings: Settings) -> ReplayReport:
    """Ставит только schema-v2 replay requests и всегда требует delivery=false."""
    if settings.delivery_enabled:
        raise RuntimeError("Migration replay запрещён при DELIVERY_ENABLED=true")
    client = firestore.Client(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    documents = list(
        client.collection("migration_replay_requests").where("state", "==", "pending").stream()
    )
    service = DealService.from_settings(settings)
    dispatcher = CloudTaskDispatcher(settings)
    enqueued = 0
    skipped = 0
    for document in documents:
        data = document.to_dict() or {}
        if (
            data.get("schema_version") != "migration-replay-request/v1"
            or data.get("delivery_enabled") is not False
            or not data.get("listing_id")
            or not data.get("content_hash")
        ):
            skipped += 1
            document.reference.set(
                {"state": "rejected", "updated_at": firestore.SERVER_TIMESTAMP}, merge=True
            )
            continue
        await dispatcher.enqueue_processing(
            str(data["listing_id"]),
            str(data["content_hash"]),
            service.decision_engine.version,
            recalculation_epoch=str(data.get("migration_id") or document.id),
        )
        document.reference.set(
            {"state": "enqueued", "updated_at": firestore.SERVER_TIMESTAMP}, merge=True
        )
        enqueued += 1
        if enqueued % 100 == 0:
            await asyncio.sleep(0)
    return ReplayReport(pending=len(documents), enqueued=enqueued, skipped=skipped)


async def run_migration_replay_direct(
    settings: Settings,
    *,
    limit: int | None = None,
    concurrency: int = 10,
) -> ReplayReport:
    """Обрабатывает catch-up напрямую в maintenance job, не включая production-очереди."""
    if settings.delivery_enabled:
        raise RuntimeError("Migration replay запрещён при DELIVERY_ENABLED=true")
    if limit is not None and limit < 1:
        raise ValueError("limit должен быть положительным")
    if concurrency < 1 or concurrency > 50:
        raise ValueError("concurrency должен находиться в диапазоне 1..50")

    client = firestore.Client(
        project=settings.google_cloud_project,
        database=settings.firestore_database,
    )
    documents = list(
        client.collection("migration_replay_requests").where("state", "==", "pending").stream()
    )
    documents.sort(key=lambda item: item.id)
    if limit is not None:
        documents = documents[:limit]
    service = DealService.from_settings(settings)
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    failed = 0
    skipped = 0

    async def process(document: object) -> str:
        reference = document.reference  # type: ignore[attr-defined]
        data = document.to_dict() or {}  # type: ignore[attr-defined]
        if (
            data.get("schema_version") != "migration-replay-request/v1"
            or data.get("delivery_enabled") is not False
            or not data.get("listing_id")
            or not data.get("content_hash")
        ):
            reference.set(
                {"state": "rejected", "updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            return "skipped"
        async with semaphore:
            reference.set(
                {"state": "processing", "updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
            try:
                listing_id = str(data["listing_id"])
                content_hash = str(data["content_hash"])
                snapshot = service.repository.get_snapshot(listing_id, content_hash)
                if (
                    snapshot is None
                    or not service.repository.is_current_snapshot(listing_id, content_hash)
                ):
                    reference.set(
                        {
                            "state": "rejected",
                            "error_type": "SnapshotNotCurrentOrMissing",
                            "updated_at": firestore.SERVER_TIMESTAMP,
                        },
                        merge=True,
                    )
                    return "skipped"
                await service.process_listing(listing_id, content_hash)
            except Exception as error:
                reference.set(
                    {
                        "state": "failed",
                        "error_type": type(error).__name__,
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    },
                    merge=True,
                )
                return "failed"
            reference.set(
                {
                    "state": "completed",
                    "error_type": firestore.DELETE_FIELD,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
            return "completed"

    results = await asyncio.gather(*(process(document) for document in documents))
    completed = results.count("completed")
    failed = results.count("failed")
    skipped = results.count("skipped")
    return ReplayReport(
        pending=len(documents),
        enqueued=0,
        skipped=skipped,
        completed=completed,
        failed=failed,
    )

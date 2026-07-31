"""Архивирование исходных HTML/JSON до нормализации и принятия решений."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from google.api_core.exceptions import PreconditionFailed
from google.cloud.storage import Client  # type: ignore[import-untyped]
from pydantic import HttpUrl

from src.domain.models import RawSnapshotMetadata
from src.storage import Repository


class RawSnapshotArchive(Protocol):
    async def save(
        self,
        source: str,
        source_url: str,
        content_type: str,
        payload: bytes,
        *,
        attempt_number: int | None = None,
    ) -> RawSnapshotMetadata: ...


class LocalRawSnapshotArchive:
    """Локальный архив для разработки с тем же metadata-контрактом."""

    def __init__(self, root: Path, repository: Repository) -> None:
        self.root = root
        self.repository = repository

    async def save(
        self,
        source: str,
        source_url: str,
        content_type: str,
        payload: bytes,
        *,
        attempt_number: int | None = None,
    ) -> RawSnapshotMetadata:
        checksum = hashlib.sha256(payload).hexdigest()
        suffix = _suffix(content_type)
        relative = Path(source) / datetime.now(UTC).strftime("%Y/%m/%d") / f"{checksum}{suffix}"
        target = self.root / relative
        await asyncio.to_thread(_write_once, target, payload)
        metadata = RawSnapshotMetadata(
            source=source,
            source_url=HttpUrl(source_url),
            storage_uri=target.resolve().as_uri(),
            checksum_sha256=checksum,
            content_type=content_type,
            size_bytes=len(payload),
        )
        await asyncio.to_thread(self.repository.save_raw_snapshot, metadata)
        if attempt_number is not None:
            await asyncio.to_thread(
                _record_raw_snapshot_attempt,
                self.repository,
                metadata,
                attempt_number,
            )
        return metadata


class GcsRawSnapshotArchive:
    """Production-архив Cloud Storage с метаданными в Repository/Firestore."""

    def __init__(self, project_id: str, bucket_name: str, repository: Repository) -> None:
        if not bucket_name:
            raise ValueError("RAW_SNAPSHOTS_BUCKET обязателен для GCS-архива")
        self.bucket = Client(project=project_id).bucket(bucket_name)
        self.repository = repository

    async def save(
        self,
        source: str,
        source_url: str,
        content_type: str,
        payload: bytes,
        *,
        attempt_number: int | None = None,
    ) -> RawSnapshotMetadata:
        checksum = hashlib.sha256(payload).hexdigest()
        suffix = _suffix(content_type)
        object_name = f"raw/{source}/{datetime.now(UTC).strftime('%Y/%m/%d')}/{checksum}{suffix}"
        blob = self.bucket.blob(object_name)
        await asyncio.to_thread(_upload_once, blob, payload, content_type)
        metadata = RawSnapshotMetadata(
            source=source,
            source_url=HttpUrl(source_url),
            storage_uri=f"gs://{self.bucket.name}/{object_name}",
            checksum_sha256=checksum,
            content_type=content_type,
            size_bytes=len(payload),
        )
        await asyncio.to_thread(self.repository.save_raw_snapshot, metadata)
        if attempt_number is not None:
            await asyncio.to_thread(
                _record_raw_snapshot_attempt,
                self.repository,
                metadata,
                attempt_number,
            )
        return metadata


def _record_raw_snapshot_attempt(
    repository: Repository,
    metadata: RawSnapshotMetadata,
    attempt_number: int,
) -> None:
    """Связывает каждый HTTP-захват с дедуплицированным immutable payload."""
    if attempt_number < 1:
        raise ValueError("Номер попытки raw snapshot должен быть положительным")
    repository.record_audit_event(
        "raw_snapshot_attempt",
        {
            "attempt_number": attempt_number,
            "source": metadata.source,
            "source_url": str(metadata.source_url),
            "checksum_sha256": metadata.checksum_sha256,
            "storage_uri": metadata.storage_uri,
            "content_type": metadata.content_type,
            "size_bytes": metadata.size_bytes,
            "fetched_at": metadata.fetched_at.isoformat(),
        },
    )


def _write_once(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)


def _upload_once(blob: object, payload: bytes, content_type: str) -> None:
    """Атомарно создаёт immutable GCS object без предварительного GET."""
    try:
        blob.upload_from_string(  # type: ignore[attr-defined]
            payload,
            content_type=content_type,
            if_generation_match=0,
        )
    except PreconditionFailed:
        # Такой checksum уже заархивирован; перезапись запрещена контрактом.
        return


def _suffix(content_type: str) -> str:
    lowered = content_type.casefold()
    if "json" in lowered:
        return ".json"
    if "html" in lowered:
        return ".html"
    return ".bin"

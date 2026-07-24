"""Архивирование исходных HTML/JSON до нормализации и принятия решений."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

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
    ) -> RawSnapshotMetadata:
        checksum = hashlib.sha256(payload).hexdigest()
        suffix = _suffix(content_type)
        object_name = f"raw/{source}/{datetime.now(UTC).strftime('%Y/%m/%d')}/{checksum}{suffix}"
        blob = self.bucket.blob(object_name)
        if not await asyncio.to_thread(blob.exists):
            await asyncio.to_thread(blob.upload_from_string, payload, content_type=content_type)
        metadata = RawSnapshotMetadata(
            source=source,
            source_url=HttpUrl(source_url),
            storage_uri=f"gs://{self.bucket.name}/{object_name}",
            checksum_sha256=checksum,
            content_type=content_type,
            size_bytes=len(payload),
        )
        await asyncio.to_thread(self.repository.save_raw_snapshot, metadata)
        return metadata


def _write_once(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)


def _suffix(content_type: str) -> str:
    lowered = content_type.casefold()
    if "json" in lowered:
        return ".json"
    if "html" in lowered:
        return ".html"
    return ".bin"

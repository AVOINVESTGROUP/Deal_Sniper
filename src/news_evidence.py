"""Единый fail-closed ingestion проверяемых автомобильных новостей."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from google.api_core.exceptions import PreconditionFailed
from google.cloud.storage import Client  # type: ignore[import-untyped]
from pydantic import HttpUrl

from src.config import Settings
from src.domain.ids import canonical_hash
from src.domain.models import FreshnessStatus, NewsEvidence, NewsFeedConfiguration
from src.news import DubaiAutoNewsClient, NewsItem, canonical_news_url
from src.storage import Repository

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_BYTES = 4_096


class NewsIngestionService:
    """Проверяет provenance статьи и сохраняет immutable изображение и evidence."""

    def __init__(self, repository: Repository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def ingest(
        self,
        feeds: list[NewsFeedConfiguration],
        *,
        now: datetime | None = None,
    ) -> list[NewsEvidence]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        accepted: list[NewsEvidence] = []
        for feed in feeds:
            try:
                items = await DubaiAutoNewsClient(
                    str(feed.url),
                    self.settings.request_timeout_seconds,
                    self.settings.auto_news_max_age_days,
                    5,
                    publisher_hint=feed.publisher,
                ).latest(now=current)
                for item in items:
                    try:
                        evidence = await self._verify_item(feed, item, current)
                    except httpx.HTTPError as error:
                        await self._reject(
                            feed, item, f"asset_fetch_error:{type(error).__name__}"
                        )
                        continue
                    if evidence is None:
                        continue
                    await asyncio.to_thread(self.repository.save_news_evidence, evidence)
                    accepted.append(evidence)
                await asyncio.to_thread(
                    self.repository.record_source_run,
                    f"news:{feed.name}",
                    {"accepted": len(accepted), "fetched": len(items), "error": ""},
                )
            except (httpx.HTTPError, ValueError) as error:
                await asyncio.to_thread(
                    self.repository.record_source_run,
                    f"news:{feed.name}",
                    {"accepted": 0, "fetched": 0, "error": f"{type(error).__name__}: {error}"},
                )
        return accepted

    async def _verify_item(
        self,
        feed: NewsFeedConfiguration,
        item: NewsItem,
        current: datetime,
    ) -> NewsEvidence | None:
        publisher_domains = _domains(feed.publisher_domains) or _domains([str(feed.url)])
        image_domains = _domains(feed.image_domains) or set(publisher_domains)
        timeout = self.settings.request_timeout_seconds
        headers = {"User-Agent": "DubaiDealSniper/1.2"}
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            article = await client.get(item.url)
            article.raise_for_status()
            final_article_url = str(article.url)
            if not _allowed_domain(final_article_url, publisher_domains):
                await self._reject(feed, item, "publisher_domain_mismatch")
                return None
            image_url = item.image_url
            image_source_type = item.image_source_type
            if image_url and not _allowed_domain(image_url, image_domains):
                image_url = ""
            if not image_url:
                image_url = _page_image(article.text, final_article_url)
                image_source_type = "page_metadata"
            if not image_url or urlparse(image_url).scheme != "https":
                await self._reject(feed, item, "missing_source_backed_image")
                return None
            image = await client.get(image_url)
            if image.status_code >= 400 and image_source_type != "page_metadata":
                image_url = _page_image(article.text, final_article_url)
                image_source_type = "page_metadata"
                image = await client.get(image_url)
            image.raise_for_status()
        final_image_url = str(image.url)
        if not _allowed_domain(final_image_url, image_domains):
            await self._reject(feed, item, "image_domain_mismatch")
            return None
        content_type = image.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
        payload = image.content
        if (
            not content_type.startswith("image/")
            or len(payload) < MIN_IMAGE_BYTES
            or len(payload) > MAX_IMAGE_BYTES
            or not _valid_image_signature(payload, content_type)
        ):
            await self._reject(feed, item, "invalid_image_asset")
            return None
        image_sha256 = hashlib.sha256(payload).hexdigest()
        storage_uri = await save_news_asset(self.settings, image_sha256, content_type, payload)
        canonical_url = canonical_news_url(final_article_url)
        semantic = canonical_hash(
            "news-evidence-semantic/v1",
            {
                "url": canonical_url,
                "publisher": feed.publisher.casefold(),
                "title": item.title,
                "published_at": item.published_at.isoformat(),
                "image_sha256": image_sha256,
            },
        )
        feed_revision = canonical_hash(
            "news-feed/v1",
            {
                "name": feed.name,
                "publisher": feed.publisher,
                "url": str(feed.url),
                "publisher_domains": sorted(publisher_domains),
                "image_domains": sorted(image_domains),
            },
        )
        source_item_sha = hashlib.sha256(
            f"{item.title}\n{item.url}\n{item.published_at.isoformat()}\n{item.summary}".encode()
        ).hexdigest()
        valid_until = current + timedelta(days=self.settings.auto_news_max_age_days)
        evidence_id = canonical_hash("news-evidence/v1", {"semantic": semantic})
        existing = await asyncio.to_thread(self.repository.get_news_evidence, evidence_id)
        evidence_created_at = existing.evidence_created_at if existing else current
        return NewsEvidence(
            evidence_id=evidence_id,
            semantic_fingerprint=semantic,
            feed_id=feed.name,
            feed_revision_id=feed_revision,
            publisher_name=feed.publisher,
            publisher_domains=sorted(publisher_domains),
            source_url=HttpUrl(item.url),
            canonical_url=HttpUrl(canonical_url),
            title=item.title,
            summary=item.summary,
            published_at=item.published_at,
            image_source_url=HttpUrl(image_url),
            image_final_url=HttpUrl(final_image_url),
            image_storage_uri=storage_uri,
            image_sha256=image_sha256,
            image_content_type=content_type,
            image_size_bytes=len(payload),
            image_source_type=image_source_type,
            source_item_sha256=source_item_sha,
            evidence_created_at=evidence_created_at,
            fetched_at=current,
            last_checked_at=current,
            valid_until=valid_until,
            freshness_status=FreshnessStatus.ACTIVE,
        )

    async def _reject(self, feed: NewsFeedConfiguration, item: NewsItem, reason: str) -> None:
        await asyncio.to_thread(
            self.repository.record_audit_event,
            "news_evidence_rejected",
            {"feed_id": feed.name, "url": item.url, "reason": reason},
        )


def evidence_as_news_item(evidence: NewsEvidence) -> NewsItem:
    return NewsItem(
        title=evidence.title,
        publisher=evidence.publisher_name,
        url=str(evidence.canonical_url),
        published_at=evidence.published_at,
        summary=evidence.summary,
        image_url=str(evidence.image_final_url),
        image_source_type=evidence.image_source_type,
    )


async def save_news_asset(
    settings: Settings, checksum: str, content_type: str, payload: bytes
) -> str:
    suffix = _image_suffix(content_type)
    if settings.storage_backend == "firestore":
        if not settings.raw_snapshots_bucket:
            raise ValueError("RAW_SNAPSHOTS_BUCKET обязателен для news assets")
        bucket = Client(project=settings.google_cloud_project).bucket(settings.raw_snapshots_bucket)
        object_name = f"news-assets/{checksum}{suffix}"
        blob = bucket.blob(object_name)
        try:
            await asyncio.to_thread(
                blob.upload_from_string,
                payload,
                content_type=content_type,
                if_generation_match=0,
            )
        except PreconditionFailed:
            pass
        return f"gs://{bucket.name}/{object_name}"
    target = settings.local_raw_snapshots_path / "news-assets" / f"{checksum}{suffix}"
    await asyncio.to_thread(_write_once, target, payload)
    return target.resolve().as_uri()


async def load_news_asset(settings: Settings, storage_uri: str) -> bytes:
    if storage_uri.startswith("gs://"):
        bucket_name, object_name = storage_uri[5:].split("/", maxsplit=1)
        blob = Client(project=settings.google_cloud_project).bucket(bucket_name).blob(object_name)
        return await asyncio.to_thread(blob.download_as_bytes)
    if storage_uri.startswith("file:"):
        from urllib.request import url2pathname

        raw_path = url2pathname(urlparse(storage_uri).path)
        if os.name == "nt" and raw_path.startswith("/"):
            raw_path = raw_path[1:]
        path = Path(raw_path)
        return await asyncio.to_thread(path.read_bytes)
    raise ValueError("Неподдерживаемый news asset URI")


def _domains(values: list[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        if parsed.hostname:
            result.add(parsed.hostname.casefold())
    return result


def _allowed_domain(url: str, allowed: set[str]) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return bool(host and any(host == domain or host.endswith(f".{domain}") for domain in allowed))


def _page_image(document: str, base_url: str) -> str:
    soup = BeautifulSoup(document, "html.parser")
    for attribute, value in (("property", "og:image"), ("name", "twitter:image")):
        node = soup.find("meta", attrs={attribute: value})
        if node is not None:
            candidate = str(node.get("content") or "").strip()
            if candidate:
                if candidate.startswith("//"):
                    return f"https:{candidate}"
                if not urlparse(candidate).scheme and "." in candidate.split("/", maxsplit=1)[0]:
                    return f"https://{candidate}"
                return urljoin(base_url, candidate)
    return ""


def _valid_image_signature(payload: bytes, content_type: str) -> bool:
    signatures = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/gif": (b"GIF87a", b"GIF89a"),
        "image/webp": (b"RIFF",),
    }
    return any(payload.startswith(prefix) for prefix in signatures.get(content_type, ()))


def _image_suffix(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(content_type, ".bin")


def _write_once(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)

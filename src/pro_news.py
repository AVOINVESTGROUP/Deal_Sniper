"""Проверяемая идемпотентная публикация новостей в Pro-канал."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from src.config import Settings
from src.domain.ids import canonical_hash, delivery_id, publication_revision_id
from src.domain.models import (
    NewsFeedConfiguration,
    OutboxRecord,
    OutboxState,
    PublicationEvent,
)
from src.news import DubaiAutoNewsClient, NewsItem
from src.storage import Repository

logger = logging.getLogger(__name__)

PRO_NEWS_TEMPLATE_VERSION = "pro-news/v1"
PRO_NEWS_EVENT_TYPE = "dubai-auto-news-pro"


class ContentDispatcher(Protocol):
    """Минимальный контракт постановки контентной доставки."""

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class ProNewsPublicationSummary:
    """Результат preview или запуска новостного контура."""

    enabled: bool = False
    interval_open: bool = False
    feeds: int = 0
    fetched: int = 0
    unpublished: int = 0
    selected: int = 0
    created: int = 0
    requeued: int = 0
    skipped: int = 0
    failures: int = 0
    pending: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    unknown: int = 0
    ai_used: bool = False
    preview: str = ""

    def public_dict(self) -> dict[str, bool | int | str]:
        return asdict(self)


def configured_news_feeds(
    repository: Repository,
    settings: Settings,
) -> list[NewsFeedConfiguration]:
    """Возвращает включённый registry либо environment baseline."""
    configured = [item for item in repository.list_news_feed_configurations() if item.enabled]
    if configured:
        return configured
    if not settings.auto_news_rss_url:
        return []
    return [
        NewsFeedConfiguration.model_validate(
            {
                "name": "environment-default",
                "publisher": "Google News",
                "url": settings.auto_news_rss_url,
                "enabled": True,
            }
        )
    ]


async def collect_news_items(
    feeds: list[NewsFeedConfiguration],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> list[NewsItem]:
    """Параллельно читает проверенные ленты и объединяет статьи по fingerprint."""
    clients = [
        DubaiAutoNewsClient(
            str(feed.url),
            settings.request_timeout_seconds,
            settings.auto_news_max_age_days,
            5,
            publisher_hint=feed.publisher,
        )
        for feed in feeds
    ]
    batches = await asyncio.gather(
        *(client.latest(now=now) for client in clients),
        return_exceptions=True,
    )
    unique: dict[str, NewsItem] = {}
    for batch in batches:
        if isinstance(batch, BaseException):
            continue
        for item in batch:
            unique.setdefault(item.fingerprint, item)
    return sorted(unique.values(), key=lambda item: item.published_at, reverse=True)


def _news_outbox_records(repository: Repository) -> list[OutboxRecord]:
    return [
        record
        for record in repository.list_outbox(limit=500)
        if record.template_version == PRO_NEWS_TEMPLATE_VERSION
    ]


def _published_news_fingerprints(records: list[OutboxRecord]) -> set[str]:
    fingerprints: set[str] = set()
    for record in records:
        if record.state is OutboxState.PENDING:
            continue
        values = record.payload.get("news_fingerprints", [])
        if isinstance(values, list):
            fingerprints.update(str(value) for value in values)
    return fingerprints


def _state_counts(records: list[OutboxRecord]) -> dict[OutboxState, int]:
    return {state: sum(record.state is state for record in records) for state in OutboxState}


def _last_news_publication(repository: Repository) -> datetime | None:
    for event in repository.list_audit_events(500):
        if event.get("event_type") != "pro_news_publication":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or not payload.get("selected"):
            continue
        value = event.get("created_at")
        if isinstance(value, datetime):
            return value.astimezone(UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is not None:
                return parsed.astimezone(UTC)
    return None


def _interval_open(repository: Repository, settings: Settings, now: datetime) -> bool:
    previous = _last_news_publication(repository)
    return previous is None or previous + timedelta(
        hours=settings.pro_news_min_interval_hours
    ) <= now


def format_pro_news_digest(items: list[NewsItem], introduction: str = "") -> str:
    """Формирует англоязычный digest только из проверенных фактов и ссылок."""
    lines = ["<b>Dubai & UAE Automotive Brief</b>"]
    if introduction:
        lines.extend(["", html.escape(introduction.strip())])
    lines.append("")
    for item in items:
        lines.extend(
            [
                f'• <a href="{html.escape(item.url, quote=True)}">'
                f"{html.escape(item.title)}</a>",
                f"  {html.escape(item.publisher)} · {item.published_at:%d %b %Y}",
                "",
            ]
        )
    lines.append("Verified source links are included for the full context.")
    return "\n".join(lines)


async def _vertex_introduction(items: list[NewsItem], settings: Settings) -> str:
    if (
        not settings.pro_news_ai_summary_enabled
        or not settings.vertex_ai_model
        or not settings.google_cloud_project
    ):
        return ""
    evidence = [
        {
            "title": item.title,
            "publisher": item.publisher,
            "published_at": item.published_at.date().isoformat(),
            "url": item.url,
            "summary": item.summary[:1_000],
        }
        for item in items
    ]
    prompt = (
        "Write one concise English sentence explaining why these sourced Dubai/UAE "
        "automotive headlines matter to car buyers. Use only the supplied evidence. "
        "Do not add numbers, dates, prices, quotes, URLs or events. Return plain text only.\n"
        + json.dumps(evidence, ensure_ascii=False)
    )
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            token_response = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/"
                "service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
            )
            token_response.raise_for_status()
            access_token = str(token_response.json()["access_token"])
            location = settings.vertex_ai_location
            host = "aiplatform.googleapis.com" if location == "global" else (
                f"{location}-aiplatform.googleapis.com"
            )
            endpoint = (
                f"https://{host}/v1/projects/{settings.google_cloud_project}/locations/"
                f"{location}/publishers/google/models/{settings.vertex_ai_model}:generateContent"
            )
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 120},
                },
            )
            response.raise_for_status()
        text = str(response.json()["candidates"][0]["content"]["parts"][0]["text"]).strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        logger.warning("Vertex AI summary недоступен; используется детерминированный digest")
        return ""
    if len(text) > 500 or "http" in text.casefold() or "<" in text or ">" in text:
        return ""
    if re.search(r"\d", text):
        return ""
    return text


async def preview_pro_news_publication(
    repository: Repository,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> tuple[ProNewsPublicationSummary, list[NewsItem]]:
    """Читает ленты и строит preview без записи или постановки задач."""
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    feeds = configured_news_feeds(repository, settings)
    if not settings.pro_news_enabled or not settings.telegram_pro_channel_id:
        return ProNewsPublicationSummary(enabled=False, feeds=len(feeds)), []
    items = await collect_news_items(feeds, settings, now=current_time)
    records = await asyncio.to_thread(_news_outbox_records, repository)
    published = _published_news_fingerprints(records)
    counts = _state_counts(records)
    unpublished = [item for item in items if item.fingerprint not in published]
    selected = unpublished[: settings.pro_news_max_items]
    interval_open = await asyncio.to_thread(
        _interval_open, repository, settings, current_time
    )
    preview = format_pro_news_digest(selected) if selected else ""
    return (
        ProNewsPublicationSummary(
            enabled=True,
            interval_open=interval_open,
            feeds=len(feeds),
            fetched=len(items),
            unpublished=len(unpublished),
            pending=counts[OutboxState.PENDING],
            sending=counts[OutboxState.SENDING],
            sent=counts[OutboxState.SENT],
            failed=counts[OutboxState.FAILED],
            unknown=counts[OutboxState.UNKNOWN],
            preview=preview,
        ),
        selected,
    )


async def reconcile_pro_news_publication(
    repository: Repository,
    settings: Settings,
    dispatcher: ContentDispatcher,
    *,
    now: datetime | None = None,
) -> ProNewsPublicationSummary:
    """Создаёт максимум один новый digest и не повторяет использованные статьи."""
    existing_records = await asyncio.to_thread(_news_outbox_records, repository)
    pending_records = [
        record for record in existing_records if record.state is OutboxState.PENDING
    ]
    if settings.pro_news_enabled and settings.telegram_pro_channel_id and pending_records:
        record = pending_records[0]
        failures = 0
        requeued = 0
        try:
            await dispatcher.enqueue_content_delivery(dict(record.payload))
            requeued = 1
        except Exception:
            failures = 1
        counts = _state_counts(existing_records)
        result = ProNewsPublicationSummary(
            enabled=True,
            interval_open=True,
            selected=1,
            requeued=requeued,
            failures=failures,
            pending=counts[OutboxState.PENDING],
            sending=counts[OutboxState.SENDING],
            sent=counts[OutboxState.SENT],
            failed=counts[OutboxState.FAILED],
            unknown=counts[OutboxState.UNKNOWN],
        )
        await asyncio.to_thread(
            repository.record_audit_event,
            "pro_news_publication",
            result.public_dict(),
        )
        return result

    preview, items = await preview_pro_news_publication(
        repository, settings, now=now
    )
    if not preview.enabled or not items or not preview.interval_open:
        await asyncio.to_thread(
            repository.record_audit_event,
            "pro_news_publication",
            preview.public_dict(),
        )
        return preview
    recipient = settings.telegram_pro_channel_id or ""
    digest_identity = canonical_hash(
        "pro-news-digest/v1",
        {"fingerprints": [item.fingerprint for item in items]},
    )
    event_id = publication_revision_id(
        decision_id_value=digest_identity,
        vehicle_id="dubai-auto-news",
        event_type=PRO_NEWS_EVENT_TYPE,
        recipient_id=recipient,
        template_version=PRO_NEWS_TEMPLATE_VERSION,
    )
    stable_delivery_id = delivery_id(
        decision_id_value=event_id,
        recipient_id=recipient,
        template_version=PRO_NEWS_TEMPLATE_VERSION,
        format_name="telegram-content",
    )
    existing = await asyncio.to_thread(repository.get_outbox, stable_delivery_id)
    created = requeued = selected_count = skipped = failures = 0
    ai_used = False
    try:
        if existing is not None and existing.state is not OutboxState.PENDING:
            skipped = 1
        else:
            if existing is None:
                introduction = await _vertex_introduction(items, settings)
                ai_used = bool(introduction)
                text = format_pro_news_digest(items, introduction)
                payload: dict[str, object] = {
                    "delivery_id": stable_delivery_id,
                    "publication_event_id": event_id,
                    "target_id": recipient,
                    "text": text,
                    "template_version": PRO_NEWS_TEMPLATE_VERSION,
                    "news_fingerprints": [item.fingerprint for item in items],
                    "news_urls": [item.url for item in items],
                    "ai_summary_used": ai_used,
                }
                existing = await asyncio.to_thread(
                    repository.commit_publication_with_outbox,
                    PublicationEvent(
                        publication_event_id=event_id,
                        decision_id=digest_identity,
                        vehicle_id="dubai-auto-news",
                        recipient=recipient,
                        event_type=PRO_NEWS_EVENT_TYPE,
                        template_version=PRO_NEWS_TEMPLATE_VERSION,
                    ),
                    OutboxRecord(
                        delivery_id=stable_delivery_id,
                        decision_id=digest_identity,
                        recipient=recipient,
                        template_version=PRO_NEWS_TEMPLATE_VERSION,
                        format="telegram-content",
                        payload=payload,
                    ),
                )
                created = 1
            else:
                requeued = 1
            await dispatcher.enqueue_content_delivery(dict(existing.payload))
            selected_count = 1
    except Exception:
        failures = 1
    result = ProNewsPublicationSummary(
        enabled=preview.enabled,
        interval_open=preview.interval_open,
        feeds=preview.feeds,
        fetched=preview.fetched,
        unpublished=preview.unpublished,
        selected=selected_count,
        created=created,
        requeued=requeued,
        skipped=skipped,
        failures=failures,
        ai_used=ai_used,
        pending=preview.pending,
        sending=preview.sending,
        sent=preview.sent,
        failed=preview.failed,
        unknown=preview.unknown,
        preview=preview.preview,
    )
    await asyncio.to_thread(
        repository.record_audit_event,
        "pro_news_publication",
        result.public_dict(),
    )
    return result

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
from src.domain.ids import delivery_id, publication_revision_id
from src.domain.models import (
    NewsEvidence,
    NewsFeedConfiguration,
    OutboxRecord,
    OutboxState,
    PublicationEvent,
)
from src.news import DubaiAutoNewsClient, NewsItem
from src.news_evidence import NewsIngestionService, evidence_as_news_item
from src.storage import Repository

logger = logging.getLogger(__name__)

PRO_NEWS_TEMPLATE_VERSION = "pro-news/v2"
FREE_NEWS_TEMPLATE_VERSION = "free-news/v1"
PRO_NEWS_EVENT_TYPE = "dubai-auto-news-pro"
NEWS_PAIR_READY_EVENT = "news_pair_ready"
NEWS_PAIR_BLOCKED_EVENT = "news_pair_blocked"


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
    paired_pending: int = 0
    paired_enqueued: int = 0
    blocked_pair: int = 0
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
                "publisher": "DubiCars",
                "url": settings.auto_news_rss_url,
                "publisher_domains": ["dubicars.com", "www.dubicars.com"],
                "image_domains": ["d3jvxfsgjxj1vz.cloudfront.net"],
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
        if record.template_version in {PRO_NEWS_TEMPLATE_VERSION, FREE_NEWS_TEMPLATE_VERSION}
    ]


def _published_news_fingerprints(records: list[OutboxRecord]) -> set[str]:
    fingerprints: set[str] = set()
    for record in records:
        if record.state is OutboxState.PENDING:
            continue
        if record.template_version != PRO_NEWS_TEMPLATE_VERSION:
            continue
        values = record.payload.get("news_fingerprints", [])
        if isinstance(values, list):
            fingerprints.update(str(value) for value in values)
    return fingerprints


def _state_counts(records: list[OutboxRecord]) -> dict[OutboxState, int]:
    return {state: sum(record.state is state for record in records) for state in OutboxState}


def _news_evidence_id(record: OutboxRecord) -> str:
    return str(record.payload.get("news_evidence_id") or record.decision_id)


def _news_groups(records: list[OutboxRecord]) -> dict[str, list[OutboxRecord]]:
    groups: dict[str, list[OutboxRecord]] = {}
    for record in records:
        groups.setdefault(_news_evidence_id(record), []).append(record)
    return groups


def _single_payload_value(record: OutboxRecord, key: str) -> str:
    value = record.payload.get(key)
    if isinstance(value, list):
        return str(value[0]) if len(value) == 1 else ""
    return str(value or "")


def _validate_news_pair(
    records: list[OutboxRecord],
    settings: Settings,
) -> tuple[OutboxRecord | None, OutboxRecord | None, str | None]:
    """Проверяет, что Free и Pro являются двумя представлениями одного evidence."""
    if len(records) != 2:
        return None, None, "pair_requires_exactly_two_records"
    by_template = {record.template_version: record for record in records}
    if set(by_template) != {FREE_NEWS_TEMPLATE_VERSION, PRO_NEWS_TEMPLATE_VERSION}:
        return None, None, "pair_requires_free_and_pro_templates"
    free = by_template[FREE_NEWS_TEMPLATE_VERSION]
    pro = by_template[PRO_NEWS_TEMPLATE_VERSION]
    if free.delivery_id == pro.delivery_id:
        return free, pro, "pair_delivery_ids_must_differ"
    if not settings.telegram_channel_id or free.recipient != settings.telegram_channel_id:
        return free, pro, "free_recipient_mismatch"
    if not settings.telegram_pro_channel_id or pro.recipient != settings.telegram_pro_channel_id:
        return free, pro, "pro_recipient_mismatch"
    required_values = {
        "news_evidence_id": {_news_evidence_id(free), _news_evidence_id(pro)},
        "publisher": {
            _single_payload_value(free, "publisher"),
            _single_payload_value(pro, "publisher"),
        },
        "news_url": {
            _single_payload_value(free, "news_urls"),
            _single_payload_value(pro, "news_urls"),
        },
        "fingerprint": {
            _single_payload_value(free, "news_fingerprints"),
            _single_payload_value(pro, "news_fingerprints"),
        },
        "image_sha256": {
            _single_payload_value(free, "image_sha256"),
            _single_payload_value(pro, "image_sha256"),
        },
    }
    for field, values in required_values.items():
        if len(values) != 1 or not next(iter(values), ""):
            return free, pro, f"pair_{field}_mismatch"
    return free, pro, None


def _ready_news_pairs(repository: Repository) -> dict[str, set[str]]:
    ready: dict[str, set[str]] = {}
    for event in repository.list_audit_events(1_000):
        if event.get("event_type") != NEWS_PAIR_READY_EVENT:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        evidence_id = str(payload.get("news_evidence_id") or "")
        delivery_ids = payload.get("delivery_ids")
        if evidence_id and isinstance(delivery_ids, list):
            ready[evidence_id] = {str(value) for value in delivery_ids}
    return ready


def news_pair_delivery_gate(
    repository: Repository,
    settings: Settings,
    delivery_id_value: str,
    evidence_id: str,
) -> tuple[bool, bool, str]:
    """Не допускает отправку новости до готовности пары и Pro-предшественника."""
    records = _news_groups(_news_outbox_records(repository)).get(evidence_id, [])
    free, pro, error = _validate_news_pair(records, settings)
    if error or free is None or pro is None:
        return False, True, error or "invalid_pair"
    if delivery_id_value not in {free.delivery_id, pro.delivery_id}:
        return False, True, "delivery_not_in_pair"
    expected_ids = {free.delivery_id, pro.delivery_id}
    if _ready_news_pairs(repository).get(evidence_id) != expected_ids:
        return False, False, "pair_not_enqueued"
    if delivery_id_value == free.delivery_id:
        if pro.state is OutboxState.SENT and pro.telegram_message_id:
            return True, False, "ready"
        if pro.state in {OutboxState.FAILED, OutboxState.UNKNOWN}:
            return False, True, f"pro_terminal_{pro.state.value}"
        return False, False, "pro_not_sent"
    return True, False, "ready"


def _pair_metrics(
    repository: Repository,
    settings: Settings,
    records: list[OutboxRecord],
) -> tuple[int, int, int]:
    ready = _ready_news_pairs(repository)
    paired_pending = paired_enqueued = blocked = 0
    for evidence_id, group in _news_groups(records).items():
        if not any(record.state is OutboxState.PENDING for record in group):
            continue
        free, pro, error = _validate_news_pair(group, settings)
        terminal = any(
            record.state in {OutboxState.FAILED, OutboxState.UNKNOWN} for record in group
        )
        if error or free is None or pro is None or terminal:
            blocked += 1
        elif ready.get(evidence_id) == {free.delivery_id, pro.delivery_id}:
            paired_enqueued += 1
        else:
            paired_pending += 1
    return paired_pending, paired_enqueued, blocked


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
    if (
        not settings.pro_news_enabled
        or not settings.telegram_pro_channel_id
        or not settings.telegram_channel_id
    ):
        return ProNewsPublicationSummary(enabled=False, feeds=len(feeds)), []
    await NewsIngestionService(repository, settings).ingest(feeds, now=current_time)
    evidence = await asyncio.to_thread(
        repository.active_news_evidence,
        max(20, settings.pro_news_max_items * 4),
        current_time,
    )
    records = await asyncio.to_thread(_news_outbox_records, repository)
    published = _published_news_fingerprints(records)
    counts = _state_counts(records)
    paired_pending, paired_enqueued, blocked_pair = await asyncio.to_thread(
        _pair_metrics, repository, settings, records
    )
    unpublished_evidence = [
        item for item in evidence if item.semantic_fingerprint not in published
    ]
    selected_evidence = unpublished_evidence[: settings.pro_news_max_items]
    selected = [evidence_as_news_item(item) for item in selected_evidence]
    interval_open = await asyncio.to_thread(
        _interval_open, repository, settings, current_time
    )
    preview = format_pro_news_digest(selected) if selected else ""
    return (
        ProNewsPublicationSummary(
            enabled=True,
            interval_open=interval_open,
            feeds=len(feeds),
            fetched=len(evidence),
            unpublished=len(unpublished_evidence),
            pending=counts[OutboxState.PENDING],
            sending=counts[OutboxState.SENDING],
            sent=counts[OutboxState.SENT],
            failed=counts[OutboxState.FAILED],
            unknown=counts[OutboxState.UNKNOWN],
            paired_pending=paired_pending,
            paired_enqueued=paired_enqueued,
            blocked_pair=blocked_pair,
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
    pending_groups = [
        (evidence_id, group)
        for evidence_id, group in _news_groups(existing_records).items()
        if any(record.state is OutboxState.PENDING for record in group)
    ]
    if settings.pro_news_enabled and pending_groups:
        evidence_id, group = sorted(pending_groups, key=lambda item: item[0])[0]
        free, pro, validation_error = _validate_news_pair(group, settings)
        failures = requeued = paired_pending = paired_enqueued = blocked_pair = 0
        terminal = any(
            record.state in {OutboxState.FAILED, OutboxState.UNKNOWN} for record in group
        )
        if validation_error or free is None or pro is None or terminal:
            failures = blocked_pair = 1
            await asyncio.to_thread(
                repository.record_audit_event,
                NEWS_PAIR_BLOCKED_EVENT,
                {
                    "news_evidence_id": evidence_id,
                    "delivery_ids": [record.delivery_id for record in group],
                    "reason": validation_error or "terminal_pair_state",
                },
            )
        elif not settings.delivery_enabled:
            paired_pending = 1
        elif (await asyncio.to_thread(_ready_news_pairs, repository)).get(evidence_id) == {
            free.delivery_id,
            pro.delivery_id,
        }:
            paired_enqueued = 1
        else:
            try:
                # Pro ставится первым; Free delivery дополнительно ждёт sent-состояние Pro.
                await dispatcher.enqueue_content_delivery(dict(pro.payload))
                await dispatcher.enqueue_content_delivery(dict(free.payload))
                await asyncio.to_thread(
                    repository.record_audit_event,
                    NEWS_PAIR_READY_EVENT,
                    {
                        "news_evidence_id": evidence_id,
                        "delivery_ids": [pro.delivery_id, free.delivery_id],
                        "publisher": _single_payload_value(pro, "publisher"),
                        "url": _single_payload_value(pro, "news_urls"),
                        "fingerprint": _single_payload_value(pro, "news_fingerprints"),
                        "image_sha256": _single_payload_value(pro, "image_sha256"),
                    },
                )
                requeued = 2
                paired_enqueued = 1
            except Exception as error:
                failures = blocked_pair = 1
                await asyncio.to_thread(
                    repository.record_audit_event,
                    NEWS_PAIR_BLOCKED_EVENT,
                    {
                        "news_evidence_id": evidence_id,
                        "delivery_ids": [pro.delivery_id, free.delivery_id],
                        "reason": f"enqueue_failure:{type(error).__name__}",
                    },
                )
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
            paired_pending=paired_pending,
            paired_enqueued=paired_enqueued,
            blocked_pair=blocked_pair,
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
    evidence_by_url = {
        str(item.canonical_url): item
        for item in await asyncio.to_thread(
            repository.active_news_evidence,
            max(20, settings.pro_news_max_items * 4),
            now or datetime.now(UTC),
        )
    }
    selected_evidence = [
        evidence_by_url[item.url]
        for item in items
        if item.url in evidence_by_url
    ]
    created = requeued = selected_count = skipped = failures = 0
    paired_pending = paired_enqueued = blocked_pair = 0
    ai_used = False
    # Один bounded news cycle всегда работает только с одной factual revision.
    for evidence in selected_evidence[:1]:
        introduction = await _vertex_introduction([evidence_as_news_item(evidence)], settings)
        ai_used = ai_used or bool(introduction)
        targets = [
            (settings.telegram_pro_channel_id, PRO_NEWS_TEMPLATE_VERSION, introduction),
            (settings.telegram_channel_id, FREE_NEWS_TEMPLATE_VERSION, ""),
        ]
        committed: list[OutboxRecord] = []
        for recipient, template_version, context in targets:
            if not recipient:
                failures += 1
                continue
            try:
                record, was_created = await asyncio.to_thread(
                    _commit_news_card,
                    repository,
                    evidence,
                    recipient,
                    template_version,
                    context,
                )
                committed.append(record)
                created += int(was_created)
                skipped += int(record.state is not OutboxState.PENDING)
            except Exception:
                failures += 1
        free, pro, validation_error = _validate_news_pair(committed, settings)
        if validation_error or free is None or pro is None:
            blocked_pair += 1
            await asyncio.to_thread(
                repository.record_audit_event,
                NEWS_PAIR_BLOCKED_EVENT,
                {
                    "news_evidence_id": evidence.evidence_id,
                    "delivery_ids": [record.delivery_id for record in committed],
                    "reason": validation_error or "pair_commit_failure",
                },
            )
            continue
        if not settings.delivery_enabled:
            selected_count = 1
            paired_pending = 1
            continue
        try:
            await dispatcher.enqueue_content_delivery(dict(pro.payload))
            await dispatcher.enqueue_content_delivery(dict(free.payload))
            await asyncio.to_thread(
                repository.record_audit_event,
                NEWS_PAIR_READY_EVENT,
                {
                    "news_evidence_id": evidence.evidence_id,
                    "delivery_ids": [pro.delivery_id, free.delivery_id],
                    "publisher": evidence.publisher_name,
                    "url": str(evidence.canonical_url),
                    "fingerprint": evidence.semantic_fingerprint,
                    "image_sha256": evidence.image_sha256,
                },
            )
            requeued += 2 - created
            selected_count = 1
            paired_enqueued = 1
        except Exception as error:
            failures += 1
            blocked_pair = 1
            await asyncio.to_thread(
                repository.record_audit_event,
                NEWS_PAIR_BLOCKED_EVENT,
                {
                    "news_evidence_id": evidence.evidence_id,
                    "delivery_ids": [pro.delivery_id, free.delivery_id],
                    "reason": f"enqueue_failure:{type(error).__name__}",
                },
            )
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
        paired_pending=paired_pending,
        paired_enqueued=paired_enqueued,
        blocked_pair=blocked_pair,
        preview=preview.preview,
    )
    await asyncio.to_thread(
        repository.record_audit_event,
        "pro_news_publication",
        result.public_dict(),
    )
    return result


def _commit_news_card(
    repository: Repository,
    evidence: NewsEvidence,
    recipient: str,
    template_version: str,
    introduction: str,
) -> tuple[OutboxRecord, bool]:
    event_id = publication_revision_id(
        decision_id_value=evidence.evidence_id,
        vehicle_id=f"news:{evidence.evidence_id}",
        event_type=PRO_NEWS_EVENT_TYPE,
        recipient_id=recipient,
        template_version=template_version,
    )
    stable_delivery_id = delivery_id(
        decision_id_value=event_id,
        recipient_id=recipient,
        template_version=template_version,
        format_name="telegram-photo",
    )
    existing = repository.get_outbox(stable_delivery_id)
    if existing is not None:
        return existing, False
    item = evidence_as_news_item(evidence)
    if template_version == PRO_NEWS_TEMPLATE_VERSION:
        text = format_pro_news_digest([item], introduction)
    else:
        summary = html.escape(evidence.summary[:280])
        text = (
            f"<b>{html.escape(evidence.title)}</b>\n"
            f"{html.escape(evidence.publisher_name)} · {evidence.published_at:%d %b %Y}"
            + (f"\n\n{summary}" if summary else "")
        )
    payload: dict[str, object] = {
        "delivery_id": stable_delivery_id,
        "publication_event_id": event_id,
        "target_id": recipient,
        "text": text,
        "template_version": template_version,
        "news_fingerprints": [evidence.semantic_fingerprint],
        "news_evidence_id": evidence.evidence_id,
        "news_urls": [str(evidence.canonical_url)],
        "article_button_label": "Read article",
        "article_button_url": str(evidence.canonical_url),
        "image_storage_uri": evidence.image_storage_uri,
        "image_sha256": evidence.image_sha256,
        "image_content_type": evidence.image_content_type,
        "publisher": evidence.publisher_name,
        "ai_summary_used": bool(introduction),
    }
    record = repository.commit_publication_with_outbox(
        PublicationEvent(
            publication_event_id=event_id,
            decision_id=evidence.evidence_id,
            vehicle_id=f"news:{evidence.evidence_id}",
            recipient=recipient,
            event_type=PRO_NEWS_EVENT_TYPE,
            template_version=template_version,
        ),
        OutboxRecord(
            delivery_id=stable_delivery_id,
            decision_id=evidence.evidence_id,
            recipient=recipient,
            template_version=template_version,
            format="telegram-photo",
            payload=payload,
        ),
    )
    return record, True

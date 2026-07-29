"""Fail-closed публикация Free-карточек только после точной Pro-доставки."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from src.bot import format_public_teaser, validate_free_publication
from src.config import Settings
from src.domain.ids import delivery_id, publication_revision_id
from src.domain.models import OutboxRecord, OutboxState, PublicationEvent
from src.pro_cta import append_pro_cta, pro_cta_count, pro_cta_for_index
from src.pro_publication import ProPublicationCandidate, current_pro_candidates
from src.storage import Repository, snapshot_hash

FREE_TEMPLATE_VERSION = "free/v3"
FREE_EVENT_TYPE = "deal-candidate-free"


class ContentDeliveryDispatcher(Protocol):
    """Контракт постановки безопасной Free-доставки."""

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class FreePublicationSummary:
    """Результат проверки строгой связи Free с уже доставленной Pro revision."""

    pro_candidates: int = 0
    eligible: int = 0
    created: int = 0
    requeued: int = 0
    sent: int = 0
    blocked_no_pro: int = 0
    blocked_not_sent: int = 0
    blocked_revision_mismatch: int = 0
    failures: int = 0
    legacy_sent: int = 0
    legacy_matched: int = 0
    legacy_unmatched: int = 0
    legacy_manual_review: int = 0

    def public_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LegacyFreeIntegrityItem:
    """Классификация существующей Free-доставки без изменения истории."""

    delivery_id: str
    recipient: str
    telegram_message_id: str | None
    template_version: str
    classification: str


def telegram_message_url(recipient: str, message_id: str) -> str | None:
    """Строит точную Telegram-ссылку без догадок о получателе."""
    if not message_id.isdigit():
        return None
    if recipient.startswith("@") and len(recipient) > 1:
        return f"https://t.me/{recipient[1:]}/{message_id}"
    if recipient.startswith("-100") and recipient[4:].isdigit():
        return f"https://t.me/c/{recipient[4:]}/{message_id}"
    return None


def _exact_sent_pro(
    repository: Repository,
    candidate: ProPublicationCandidate,
    pro_recipient: str,
) -> tuple[OutboxRecord | None, str | None, str]:
    record = repository.get_outbox(candidate.delivery_id)
    if record is None:
        return None, None, "no_pro"
    expected_content_hash = candidate.decision.content_hash or snapshot_hash(candidate.listing)
    payload = record.payload
    exact = (
        record.template_version == "pro/v1"
        and record.recipient == pro_recipient
        and record.decision_id == candidate.decision_id
        and str(payload.get("decision_id") or record.decision_id) == candidate.decision_id
        and str(payload.get("listing_id") or "") == candidate.listing_id
        and str(payload.get("content_hash") or "") == expected_content_hash
    )
    if not exact:
        return record, None, "revision_mismatch"
    if record.state is not OutboxState.SENT or not record.telegram_message_id:
        return record, None, "not_sent"
    url = telegram_message_url(pro_recipient, record.telegram_message_id)
    if url is None:
        return record, None, "revision_mismatch"
    return record, url, "eligible"


def preview_free_pro_integrity(
    repository: Repository,
    settings: Settings,
) -> FreePublicationSummary:
    """Считает текущие блокировки и legacy-расхождения без мутаций."""
    pro_recipient = settings.telegram_pro_channel_id
    if not pro_recipient:
        return FreePublicationSummary()
    candidates = current_pro_candidates(repository, settings)
    counters = {
        "eligible": 0,
        "sent": 0,
        "blocked_no_pro": 0,
        "blocked_not_sent": 0,
        "blocked_revision_mismatch": 0,
    }
    for candidate in candidates:
        _record, _url, status = _exact_sent_pro(repository, candidate, pro_recipient)
        if status == "eligible":
            counters["eligible"] += 1
            free_event_id = publication_revision_id(
                decision_id_value=candidate.decision_id,
                vehicle_id=candidate.vehicle_id,
                event_type=FREE_EVENT_TYPE,
                recipient_id=settings.telegram_channel_id or "",
                template_version=FREE_TEMPLATE_VERSION,
            )
            free_delivery_id = delivery_id(
                decision_id_value=free_event_id,
                recipient_id=settings.telegram_channel_id or "",
                template_version=FREE_TEMPLATE_VERSION,
                format_name="telegram-content",
            )
            free_record = repository.get_outbox(free_delivery_id)
            if free_record is not None and free_record.state is OutboxState.SENT:
                counters["sent"] += 1
        else:
            counters[f"blocked_{status}"] += 1

    records = repository.list_outbox(limit=10_000)
    legacy_items = legacy_free_integrity_items(repository, records)
    legacy_sent = len(legacy_items)
    legacy_matched = sum(item.classification == "matched" for item in legacy_items)
    legacy_unmatched = sum(item.classification == "unmatched" for item in legacy_items)
    legacy_manual_review = sum(
        item.classification == "manual_review" for item in legacy_items
    )

    return FreePublicationSummary(
        pro_candidates=len(candidates),
        eligible=counters["eligible"],
        sent=counters["sent"],
        blocked_no_pro=counters["blocked_no_pro"],
        blocked_not_sent=counters["blocked_not_sent"],
        blocked_revision_mismatch=counters["blocked_revision_mismatch"],
        legacy_sent=legacy_sent,
        legacy_matched=legacy_matched,
        legacy_unmatched=legacy_unmatched,
        legacy_manual_review=legacy_manual_review,
    )


def legacy_free_integrity_items(
    repository: Repository,
    records: list[OutboxRecord] | None = None,
) -> list[LegacyFreeIntegrityItem]:
    """Возвращает доказуемую классификацию legacy Free; withdrawn не считается активным."""
    records = records if records is not None else repository.list_outbox(limit=10_000)
    sent_pro_keys = {
        (
            item.decision_id,
            str(item.payload.get("listing_id") or ""),
            str(item.payload.get("content_hash") or ""),
        )
        for item in records
        if item.template_version == "pro/v1" and item.state is OutboxState.SENT
    }
    withdrawn = {
        str(item.get("payload", {}).get("delivery_id") or "")
        for item in repository.list_audit_events(limit=10_000)
        if item.get("event_type") == "free_publication_withdrawn"
    }
    result: list[LegacyFreeIntegrityItem] = []
    for item in records:
        if item.template_version not in {"free/v2", "market-watch/v2"}:
            continue
        if item.state is not OutboxState.SENT:
            continue
        if item.delivery_id in withdrawn:
            continue
        listing_id = str(item.payload.get("listing_id") or "")
        content_hash = str(item.payload.get("content_hash") or "")
        if not listing_id or not content_hash:
            classification = "manual_review"
        elif (item.decision_id, listing_id, content_hash) in sent_pro_keys:
            classification = "matched"
        else:
            classification = "unmatched"
        result.append(
            LegacyFreeIntegrityItem(
                delivery_id=item.delivery_id,
                recipient=item.recipient,
                telegram_message_id=item.telegram_message_id,
                template_version=item.template_version,
                classification=classification,
            )
        )
    return result


async def reconcile_free_publications(
    repository: Repository,
    settings: Settings,
    dispatcher: ContentDeliveryDispatcher,
) -> FreePublicationSummary:
    """Создаёт Free только для exact Pro outbox со статусом sent."""
    free_recipient = settings.telegram_channel_id
    pro_recipient = settings.telegram_pro_channel_id
    if not free_recipient or not pro_recipient or not settings.pro_deals_enabled:
        return FreePublicationSummary()

    candidates = current_pro_candidates(repository, settings)
    counters = {
        "eligible": 0,
        "created": 0,
        "requeued": 0,
        "sent": 0,
        "blocked_no_pro": 0,
        "blocked_not_sent": 0,
        "blocked_revision_mismatch": 0,
        "failures": 0,
    }
    limit = settings.channel_max_posts_per_run
    selected = 0
    for candidate in candidates:
        pro_record, object_url, status = await asyncio.to_thread(
            _exact_sent_pro,
            repository,
            candidate,
            pro_recipient,
        )
        if status != "eligible" or pro_record is None or object_url is None:
            counters[f"blocked_{status}"] += 1
            continue
        counters["eligible"] += 1
        free_event_id = publication_revision_id(
            decision_id_value=candidate.decision_id,
            vehicle_id=candidate.vehicle_id,
            event_type=FREE_EVENT_TYPE,
            recipient_id=free_recipient,
            template_version=FREE_TEMPLATE_VERSION,
        )
        free_delivery_id = delivery_id(
            decision_id_value=free_event_id,
            recipient_id=free_recipient,
            template_version=FREE_TEMPLATE_VERSION,
            format_name="telegram-content",
        )
        existing = await asyncio.to_thread(repository.get_outbox, free_delivery_id)
        if existing is not None:
            if existing.state is OutboxState.SENT:
                counters["sent"] += 1
            elif existing.state is OutboxState.PENDING and selected < limit:
                await dispatcher.enqueue_content_delivery(dict(existing.payload))
                counters["requeued"] += 1
                selected += 1
            continue
        if selected >= limit:
            continue
        try:
            cta_index = await asyncio.to_thread(
                repository.reserve_pro_cta_variant,
                free_event_id,
                pro_cta_count(),
            )
            cta = pro_cta_for_index(cta_index)
            text = append_pro_cta(format_public_teaser(candidate.listing, "en"), cta)
            validate_free_publication(text)
            expected_content_hash = candidate.decision.content_hash or snapshot_hash(
                candidate.listing
            )
            payload: dict[str, object] = {
                "delivery_id": free_delivery_id,
                "publication_event_id": free_event_id,
                "decision_id": candidate.decision_id,
                "target_id": free_recipient,
                "listing_id": candidate.listing_id,
                "content_hash": expected_content_hash,
                "text": text,
                "template_version": FREE_TEMPLATE_VERSION,
                "format": "telegram-content",
                "image_url": str(candidate.listing.image_urls[0]),
                "parent_pro_delivery_id": pro_record.delivery_id,
                "parent_pro_message_id": pro_record.telegram_message_id,
                "parent_pro_publication_event_id": candidate.publication_event_id,
                "pro_cta_button_label": "Join Dubai Auto Deals Pro",
                "pro_cta_button_url": settings.telegram_pro_subscription_url,
                "pro_object_button_label": "Open this exact car in Pro",
                "pro_object_button_url": object_url,
                "pro_cta_variant_id": cta.variant_id,
                "pro_cta_fingerprint": cta.fingerprint,
            }
            event = PublicationEvent(
                publication_event_id=free_event_id,
                parent_publication_event_id=candidate.publication_event_id,
                parent_delivery_id=pro_record.delivery_id,
                parent_message_id=pro_record.telegram_message_id,
                decision_id=candidate.decision_id,
                vehicle_id=candidate.vehicle_id,
                listing_id=candidate.listing_id,
                content_hash=expected_content_hash,
                recipient=free_recipient,
                event_type=FREE_EVENT_TYPE,
                template_version=FREE_TEMPLATE_VERSION,
                pro_cta_variant_id=cta.variant_id,
                pro_cta_text=cta.text,
                pro_cta_button_label=cta.button_label,
                pro_cta_target=object_url,
                pro_cta_fingerprint=cta.fingerprint,
                pro_cta_template_version=cta.template_version,
            )
            stored = await asyncio.to_thread(
                repository.commit_publication_with_outbox,
                event,
                OutboxRecord(
                    delivery_id=free_delivery_id,
                    decision_id=candidate.decision_id,
                    recipient=free_recipient,
                    template_version=FREE_TEMPLATE_VERSION,
                    format="telegram-content",
                    payload=payload,
                ),
            )
            await dispatcher.enqueue_content_delivery(dict(stored.payload))
            counters["created"] += 1
            selected += 1
        except Exception:
            counters["failures"] += 1

    summary = FreePublicationSummary(pro_candidates=len(candidates), **counters)
    await asyncio.to_thread(
        repository.record_audit_event,
        "free_pro_integrity_gate",
        summary.public_dict(),
    )
    return summary

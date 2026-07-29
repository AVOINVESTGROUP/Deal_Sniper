"""Идемпотентная сверка текущих решений с публикациями Pro-канала."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from src.bot import format_card, is_publishable, select_publishable_decisions
from src.config import Settings
from src.domain.ids import delivery_id, publication_revision_id
from src.domain.models import OutboxRecord, OutboxState, PublicationEvent
from src.storage import Repository, snapshot_hash

PRO_TEMPLATE_VERSION = "pro/v1"
PRO_EVENT_TYPE = "deal-candidate-pro"


class DeliveryDispatcher(Protocol):
    """Минимальный контракт постановки Telegram-доставки."""

    async def enqueue_delivery(self, payload: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class ProPublicationSummary:
    """Проверяемый результат preview или запуска reconciliation."""

    publishable: int = 0
    sent: int = 0
    pending: int = 0
    sending: int = 0
    unknown: int = 0
    failed: int = 0
    missing: int = 0
    selected: int = 0
    created: int = 0
    requeued: int = 0
    skipped: int = 0
    failures: int = 0

    def public_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProPublicationCandidate:
    listing: Any
    decision: Any
    listing_id: str
    decision_id: str
    vehicle_id: str
    publication_event_id: str
    delivery_id: str


def _candidate(listing: Any, decision: Any, recipient: str) -> ProPublicationCandidate:
    listing_id = f"{listing.source}:{listing.source_listing_id}"
    decision_identity = decision.decision_id or listing_id
    vehicle_id = decision.vehicle_id or listing_id
    event_id = publication_revision_id(
        decision_id_value=decision_identity,
        vehicle_id=vehicle_id,
        event_type=PRO_EVENT_TYPE,
        recipient_id=recipient,
        template_version=PRO_TEMPLATE_VERSION,
    )
    stable_delivery_id = delivery_id(
        decision_id_value=decision_identity,
        recipient_id=recipient,
        template_version=PRO_TEMPLATE_VERSION,
        format_name="telegram",
    )
    return ProPublicationCandidate(
        listing=listing,
        decision=decision,
        listing_id=listing_id,
        decision_id=decision_identity,
        vehicle_id=vehicle_id,
        publication_event_id=event_id,
        delivery_id=stable_delivery_id,
    )


def current_pro_candidates(
    repository: Repository,
    settings: Settings,
) -> list[ProPublicationCandidate]:
    """Возвращает только текущие, подтверждённые решения актуальной конфигурации."""
    recipient = settings.telegram_pro_channel_id
    if not recipient or not settings.pro_deals_enabled:
        return []
    current = repository.current_decisions(10_000)
    eligible = [
        item
        for item in current
        if item[1].financial_config_version == settings.financial_config_version
        and item[1].verification_version
        and item[1].market_fingerprint
        and bool(item[0].image_urls)
        and is_publishable(item[1], settings)
    ]
    selected = select_publishable_decisions(eligible, settings, limit=len(eligible) or 1)
    return [_candidate(listing, decision, recipient) for listing, decision in selected]


def preview_pro_reconciliation(
    repository: Repository,
    settings: Settings,
) -> ProPublicationSummary:
    """Считает состояния без внешних или внутренних мутаций."""
    counts = {state.value: 0 for state in OutboxState}
    missing = 0
    candidates = current_pro_candidates(repository, settings)
    for candidate in candidates:
        existing = repository.get_outbox(candidate.delivery_id)
        if existing is None:
            missing += 1
        else:
            counts[existing.state.value] += 1
    return ProPublicationSummary(
        publishable=len(candidates),
        sent=counts[OutboxState.SENT.value],
        pending=counts[OutboxState.PENDING.value],
        sending=counts[OutboxState.SENDING.value],
        unknown=counts[OutboxState.UNKNOWN.value],
        failed=counts[OutboxState.FAILED.value],
        missing=missing,
    )


async def reconcile_pro_publications(
    repository: Repository,
    settings: Settings,
    dispatcher: DeliveryDispatcher,
) -> ProPublicationSummary:
    """Создаёт отсутствующие Pro-публикации и переочередяет только pending."""
    if not settings.pro_deals_enabled:
        return ProPublicationSummary()
    candidates = current_pro_candidates(repository, settings)
    preview = await asyncio.to_thread(preview_pro_reconciliation, repository, settings)
    limit = settings.channel_max_posts_per_run
    selected = created = requeued = skipped = failures = 0
    for candidate in candidates:
        existing = await asyncio.to_thread(repository.get_outbox, candidate.delivery_id)
        if existing is not None and existing.state is not OutboxState.PENDING:
            skipped += 1
            continue
        if selected >= limit:
            skipped += 1
            continue
        try:
            if existing is None:
                payload: dict[str, object] = {
                    "delivery_id": candidate.delivery_id,
                    "publication_event_id": candidate.publication_event_id,
                    "decision_id": candidate.decision_id,
                    "target_id": settings.telegram_pro_channel_id or "",
                    "listing_id": candidate.listing_id,
                    "content_hash": candidate.decision.content_hash
                    or snapshot_hash(candidate.listing),
                    "text": format_card(candidate.listing, candidate.decision, "en"),
                    "engine_version": candidate.decision.engine_version,
                    "template_version": PRO_TEMPLATE_VERSION,
                    "format": "telegram",
                }
                if candidate.listing.image_urls:
                    payload["image_url"] = str(candidate.listing.image_urls[0])
                event = PublicationEvent(
                    publication_event_id=candidate.publication_event_id,
                    decision_id=candidate.decision_id,
                    vehicle_id=candidate.vehicle_id,
                    recipient=settings.telegram_pro_channel_id,
                    event_type=PRO_EVENT_TYPE,
                    template_version=PRO_TEMPLATE_VERSION,
                )
                existing = await asyncio.to_thread(
                    repository.commit_publication_with_outbox,
                    event,
                    OutboxRecord(
                        delivery_id=candidate.delivery_id,
                        decision_id=candidate.decision_id,
                        recipient=settings.telegram_pro_channel_id or "",
                        template_version=PRO_TEMPLATE_VERSION,
                        format="telegram",
                        payload=payload,
                    ),
                )
                created += 1
            else:
                requeued += 1
            await dispatcher.enqueue_delivery(dict(existing.payload))
            selected += 1
        except Exception:
            failures += 1
    summary = ProPublicationSummary(
        publishable=preview.publishable,
        sent=preview.sent,
        pending=preview.pending,
        sending=preview.sending,
        unknown=preview.unknown,
        failed=preview.failed,
        missing=preview.missing,
        selected=selected,
        created=created,
        requeued=requeued,
        skipped=skipped,
        failures=failures,
    )
    await asyncio.to_thread(
        repository.record_audit_event,
        "pro_publication_reconciliation",
        summary.public_dict(),
    )
    return summary

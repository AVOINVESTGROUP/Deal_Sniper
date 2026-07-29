"""Плановая публикация Market Pulse через PublicationEvent и outbox."""

from __future__ import annotations

import asyncio

from src.bot import format_public_teaser, validate_free_publication
from src.config import Settings
from src.content import market_pulse
from src.domain.ids import (
    canonical_hash,
    delivery_id,
    publication_event_id,
)
from src.domain.models import (
    DealDecision,
    ListingSnapshot,
    OutboxRecord,
    PublicationEvent,
)
from src.free_publication import reconcile_free_publications
from src.pro_news import ProNewsPublicationSummary, reconcile_pro_news_publication
from src.pro_publication import ProPublicationSummary, reconcile_pro_publications
from src.runtime_config import effective_settings
from src.service import DealService
from src.tasks import CloudTaskDispatcher


def format_market_watch_card(listing: ListingSnapshot, decision: DealDecision) -> str:
    """Формирует Free teaser без финансовых значений и прямой ссылки."""
    if decision.market is None:
        raise ValueError("MARKET WATCH требует рыночную оценку")
    card = f"<b>MARKET WATCH</b>\n{format_public_teaser(listing, 'en')}"
    validate_free_publication(card)
    return card


async def enqueue_market_pulse(settings: Settings) -> str | None:
    target = settings.telegram_channel_id
    if not target:
        return None
    service = DealService.from_settings(settings)
    settings = effective_settings(service.repository, settings)
    report = await asyncio.to_thread(market_pulse, service.repository)
    facts_hash = canonical_hash(
        "market-pulse-facts/v1",
        {
            "period_from": report.period_from,
            "period_to": report.period_to,
            "facts": report.facts,
            "sample_size": report.sample_size,
        },
    )
    event_id = publication_event_id(
        decision_id_value=facts_hash,
        vehicle_id="market-aggregate",
        event_type="market-pulse",
    )
    event = PublicationEvent(
        publication_event_id=event_id,
        decision_id=facts_hash,
        vehicle_id="market-aggregate",
        event_type="market-pulse",
        template_version=report.template_version,
    )
    await asyncio.to_thread(service.repository.save_publication_event, event)
    stable_delivery_id = delivery_id(
        decision_id_value=event_id,
        recipient_id=target,
        template_version=report.template_version,
        format_name="telegram-content",
    )
    text = (
        "<b>UAE Used Car Market Pulse</b>\n"
        f"Period: {report.period_from.date()}–{report.period_to.date()}\n"
        f"Verified sample: {report.sample_size}\n"
        f"Median asking price: {report.facts['median_asking_price_aed']} AED\n"
        f"Most represented make: {report.facts['top_make']} "
        f"({report.facts['top_make_count']})\n\n"
        "Object alerts appear here only after the exact full card has been delivered to Pro. "
        "No unavailable or inferred vehicle is advertised.\n\n"
        "Open the bot to create a personal car search."
    )
    delivery_payload: dict[str, object] = {
        "delivery_id": stable_delivery_id,
        "publication_event_id": event_id,
        "target_id": target,
        "text": text,
        "template_version": report.template_version,
    }
    await asyncio.to_thread(
        service.repository.put_outbox,
        OutboxRecord(
            delivery_id=stable_delivery_id,
            decision_id=event_id,
            recipient=target,
            template_version=report.template_version,
            format="telegram-content",
            payload=delivery_payload,
        ),
    )
    dispatcher = CloudTaskDispatcher(settings)
    await dispatcher.enqueue_content_delivery(delivery_payload)

    return event_id


async def run_content_publication(
    settings: Settings,
) -> tuple[str | None, ProPublicationSummary, ProNewsPublicationSummary]:
    """Публикует Free-контент и независимо сверяет очередь Pro-канала."""
    service = DealService.from_settings(settings)
    current = effective_settings(service.repository, settings)
    dispatcher = CloudTaskDispatcher(current)
    pro_summary = await reconcile_pro_publications(
        service.repository,
        current,
        dispatcher,
    )
    await reconcile_free_publications(service.repository, current, dispatcher)
    news_summary = await reconcile_pro_news_publication(
        service.repository,
        current,
        dispatcher,
    )
    event_id = await enqueue_market_pulse(settings)
    return event_id, pro_summary, news_summary

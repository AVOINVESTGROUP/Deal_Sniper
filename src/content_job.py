"""Плановая публикация Market Pulse через PublicationEvent и outbox."""

from __future__ import annotations

import asyncio
import html
from decimal import Decimal

from src.config import Settings
from src.content import market_pulse
from src.domain.ids import canonical_hash, delivery_id, publication_event_id
from src.domain.models import DealDecision, ListingSnapshot, OutboxRecord, PublicationEvent
from src.service import DealService
from src.tasks import CloudTaskDispatcher

MARKET_WATCH_TEMPLATE_VERSION = "market-watch/v1"
MARKET_WATCH_BATCH_SIZE = 5


def _money(value: Decimal) -> str:
    return f"{value:,.0f}"


def format_market_watch_card(listing: ListingSnapshot, decision: DealDecision) -> str:
    """Формирует проверяемую карточку рынка без ложного инвестиционного сигнала."""
    if decision.market is None:
        raise ValueError("MARKET WATCH требует рыночную оценку")
    vehicle = " ".join(
        part for part in (listing.make, listing.model, str(listing.year or "")) if part
    ) or listing.title
    if decision.market.low_aed > 0 and listing.price_aed < decision.market.low_aed:
        difference = (decision.market.low_aed - listing.price_aed) / decision.market.low_aed * 100
        position = f"{difference:.1f}% below the verified market range"
    else:
        position = "within or above the verified market range"
    return (
        "<b>MARKET WATCH</b>\n"
        f"<b>{html.escape(vehicle)}</b>\n"
        f"Price: {_money(listing.price_aed)} AED\n"
        f"Verified market: {_money(decision.market.low_aed)}–"
        f"{_money(decision.market.high_aed)} AED\n"
        f"Position: {position}\n"
        f"Source: {html.escape(listing.source)}\n\n"
        f'<a href="{html.escape(str(listing.url), quote=True)}">Open listing</a>\n'
        "Market reference — not an investment recommendation."
    )


async def enqueue_market_pulse(settings: Settings) -> str | None:
    target = settings.telegram_channel_id
    if not target:
        return None
    service = DealService.from_settings(settings)
    report = await asyncio.to_thread(market_pulse, service.repository)
    current = await asyncio.to_thread(service.repository.current_decisions, 10_000)
    watch = [item for item in current if item[1].market is not None]
    watch.sort(
        key=lambda item: item[1].asking_price_aed / item[1].market.low_aed  # type: ignore[union-attr]
    )
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
    watch_lines = []
    for listing, decision in watch[:3]:
        assert decision.market is not None
        vehicle = " ".join(
            part for part in (listing.make, listing.model, str(listing.year or "")) if part
        )
        relation = (
            "below the verified market range"
            if listing.price_aed < decision.market.low_aed
            else "within or above the verified market range"
        )
        watch_lines.append(f"• <b>{vehicle}</b> — verified fixed price; {relation}.")
    objects = "\n".join(watch_lines) or "No vehicle currently has enough verified comparables."
    text = (
        "<b>UAE Used Car Market Pulse</b>\n"
        f"Period: {report.period_from.date()}–{report.period_to.date()}\n"
        f"Verified sample: {report.sample_size}\n"
        f"Median asking price: {report.facts['median_asking_price_aed']} AED\n"
        f"Most represented make: {report.facts['top_make']} "
        f"({report.facts['top_make_count']})\n\n"
        "<b>Market Watch</b>\n"
        f"{objects}\n\n"
        "These are verified market objects, not investment recommendations. "
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

    published = 0
    for listing, decision in watch:
        if published >= MARKET_WATCH_BATCH_SIZE:
            break
        if decision.market is None or not listing.image_urls:
            continue
        decision_identity = decision.decision_id or canonical_hash(
            "market-watch-decision/v1",
            {
                "source": listing.source,
                "source_listing_id": listing.source_listing_id,
                "content_hash": decision.content_hash,
                "market_fingerprint": decision.market_fingerprint,
            },
        )
        listing_id = f"{listing.source}:{listing.source_listing_id}"
        card_event_id = publication_event_id(
            decision_id_value=decision_identity,
            vehicle_id=decision.vehicle_id or listing_id,
            event_type="market-watch",
        )
        card_delivery_id = delivery_id(
            decision_id_value=card_event_id,
            recipient_id=target,
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
            format_name="telegram-content",
        )
        existing = await asyncio.to_thread(service.repository.get_outbox, card_delivery_id)
        if existing is not None:
            continue
        card_event = PublicationEvent(
            publication_event_id=card_event_id,
            decision_id=decision_identity,
            vehicle_id=decision.vehicle_id or listing_id,
            event_type="market-watch",
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
        )
        await asyncio.to_thread(service.repository.save_publication_event, card_event)
        card_payload: dict[str, object] = {
            "delivery_id": card_delivery_id,
            "publication_event_id": card_event_id,
            "target_id": target,
            "text": format_market_watch_card(listing, decision),
            "template_version": MARKET_WATCH_TEMPLATE_VERSION,
            "image_url": str(listing.image_urls[0]),
        }
        await asyncio.to_thread(
            service.repository.put_outbox,
            OutboxRecord(
                delivery_id=card_delivery_id,
                decision_id=decision_identity,
                recipient=target,
                template_version=MARKET_WATCH_TEMPLATE_VERSION,
                format="telegram-content",
                payload=card_payload,
            ),
        )
        await dispatcher.enqueue_content_delivery(card_payload)
        published += 1
    return event_id

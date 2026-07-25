"""Плановая публикация Market Pulse через PublicationEvent и outbox."""

from __future__ import annotations

import asyncio

from src.config import Settings
from src.content import market_pulse
from src.domain.ids import canonical_hash, delivery_id, publication_event_id
from src.domain.models import OutboxRecord, PublicationEvent
from src.service import DealService
from src.tasks import CloudTaskDispatcher


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
    await CloudTaskDispatcher(settings).enqueue_content_delivery(delivery_payload)
    return event_id

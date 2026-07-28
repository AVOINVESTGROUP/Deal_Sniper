"""Плановая публикация Market Pulse через PublicationEvent и outbox."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from src.bot import format_public_teaser, validate_free_publication
from src.config import Settings
from src.content import market_pulse
from src.domain.ids import (
    canonical_hash,
    delivery_id,
    publication_event_id,
    publication_revision_id,
)
from src.domain.models import (
    DealDecision,
    ListingSnapshot,
    OutboxRecord,
    OutboxState,
    PublicationEvent,
)
from src.pro_cta import (
    append_pro_cta,
    pro_cta_count,
    pro_cta_for_index,
    validated_subscription_url,
)
from src.pro_publication import ProPublicationSummary, reconcile_pro_publications
from src.runtime_config import effective_settings
from src.service import DealService
from src.tasks import CloudTaskDispatcher

MARKET_WATCH_TEMPLATE_VERSION = "market-watch/v2"
MARKET_WATCH_BATCH_SIZE = 5


def _money(value: Decimal) -> str:
    return f"{value:,.0f}"


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
    subscription_url = validated_subscription_url(settings.telegram_pro_subscription_url)
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
        subject_event_id = publication_event_id(
            decision_id_value=decision_identity,
            vehicle_id=decision.vehicle_id or listing_id,
            event_type="market-watch",
        )
        card_event_id = publication_revision_id(
            decision_id_value=decision_identity,
            vehicle_id=decision.vehicle_id or listing_id,
            event_type="market-watch-free",
            recipient_id=target,
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
        )
        card_delivery_id = delivery_id(
            decision_id_value=card_event_id,
            recipient_id=target,
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
            format_name="telegram-content",
        )
        existing = await asyncio.to_thread(service.repository.get_outbox, card_delivery_id)
        if existing is not None:
            if existing.state is OutboxState.PENDING:
                await dispatcher.enqueue_content_delivery(dict(existing.payload))
                published += 1
            continue
        if subscription_url is None:
            continue
        cta_index = await asyncio.to_thread(
            service.repository.reserve_pro_cta_variant,
            card_event_id,
            pro_cta_count(),
        )
        pro_cta = pro_cta_for_index(cta_index)
        card_event = PublicationEvent(
            publication_event_id=card_event_id,
            parent_publication_event_id=subject_event_id,
            decision_id=decision_identity,
            vehicle_id=decision.vehicle_id or listing_id,
            recipient=target,
            event_type="market-watch-free",
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
            pro_cta_variant_id=pro_cta.variant_id,
            pro_cta_text=pro_cta.text,
            pro_cta_button_label=pro_cta.button_label,
            pro_cta_target=subscription_url,
            pro_cta_fingerprint=pro_cta.fingerprint,
            pro_cta_template_version=pro_cta.template_version,
        )
        card_text = append_pro_cta(format_market_watch_card(listing, decision), pro_cta)
        validate_free_publication(card_text)
        card_payload: dict[str, object] = {
            "delivery_id": card_delivery_id,
            "publication_event_id": card_event_id,
            "target_id": target,
            "text": card_text,
            "template_version": MARKET_WATCH_TEMPLATE_VERSION,
            "image_url": str(listing.image_urls[0]),
            "pro_cta_button_label": pro_cta.button_label,
            "pro_cta_button_url": subscription_url,
            "pro_cta_variant_id": pro_cta.variant_id,
            "pro_cta_fingerprint": pro_cta.fingerprint,
        }
        outbox = OutboxRecord(
            delivery_id=card_delivery_id,
            decision_id=decision_identity,
            recipient=target,
            template_version=MARKET_WATCH_TEMPLATE_VERSION,
            format="telegram-content",
            payload=card_payload,
        )
        stored = await asyncio.to_thread(
            service.repository.commit_publication_with_outbox,
            card_event,
            outbox,
        )
        await dispatcher.enqueue_content_delivery(dict(stored.payload))
        published += 1
    return event_id


async def run_content_publication(
    settings: Settings,
) -> tuple[str | None, ProPublicationSummary]:
    """Публикует Free-контент и независимо сверяет очередь Pro-канала."""
    service = DealService.from_settings(settings)
    current = effective_settings(service.repository, settings)
    dispatcher = CloudTaskDispatcher(current)
    pro_summary = await reconcile_pro_publications(
        service.repository,
        current,
        dispatcher,
    )
    event_id = await enqueue_market_pulse(settings)
    return event_id, pro_summary

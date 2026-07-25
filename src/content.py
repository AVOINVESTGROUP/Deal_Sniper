"""Воспроизводимый информационный модуль на данных Repository."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.domain.models import ListingSnapshot
from src.storage import Repository


@dataclass(frozen=True, slots=True)
class ContentReport:
    kind: str
    period_from: datetime
    period_to: datetime
    sample_size: int
    facts: dict[str, str | int]
    provenance: list[str]
    template_version: str = "content/v1"


def market_pulse(repository: Repository, days: int = 7) -> ContentReport:
    """Строит Market Pulse исключительно из активных current snapshots."""
    period_to = datetime.now(UTC)
    period_from = period_to - timedelta(days=days)
    snapshots = [
        item for item in repository.latest_snapshots() if item.observed_at >= period_from
    ]
    prices = sorted(item.price_aed for item in snapshots)
    median = prices[len(prices) // 2] if prices else Decimal(0)
    makes = Counter((item.make or "Unknown") for item in snapshots)
    top_make, top_count = makes.most_common(1)[0] if makes else ("—", 0)
    return ContentReport(
        kind="market_pulse",
        period_from=period_from,
        period_to=period_to,
        sample_size=len(snapshots),
        facts={
            "median_asking_price_aed": str(median),
            "top_make": top_make,
            "top_make_count": top_count,
        },
        provenance=[
            f"{item.source}:{item.source_listing_id}:{item.observed_at.isoformat()}"
            for item in snapshots
        ],
    )


def price_drop(repository: Repository, days: int = 7) -> ContentReport:
    """Формирует подтверждаемый список снижений цены по версиям одного объявления."""
    period_to = datetime.now(UTC)
    period_from = period_to - timedelta(days=days)
    grouped: dict[str, list[ListingSnapshot]] = {}
    for item in repository.snapshot_versions():
        grouped.setdefault(f"{item.source}:{item.source_listing_id}", []).append(item)
    drops: list[tuple[str, Decimal, Decimal]] = []
    provenance: list[str] = []
    for listing_id, values in grouped.items():
        ordered = sorted(values, key=lambda item: item.observed_at)
        if len(ordered) < 2 or ordered[-1].observed_at < period_from:
            continue
        before = ordered[-2].price_aed
        after = ordered[-1].price_aed
        if after < before:
            drops.append((listing_id, before, after))
            provenance.extend(
                f"{listing_id}:{item.observed_at.isoformat()}:{item.price_aed}"
                for item in ordered[-2:]
            )
    drops.sort(key=lambda item: item[1] - item[2], reverse=True)
    largest = drops[0] if drops else ("—", Decimal(0), Decimal(0))
    return ContentReport(
        kind="price_drop",
        period_from=period_from,
        period_to=period_to,
        sample_size=len(drops),
        facts={
            "drop_count": len(drops),
            "largest_drop_listing": largest[0],
            "largest_drop_aed": str(largest[1] - largest[2]),
        },
        provenance=provenance,
        template_version="price-drop/v1",
    )


def weekly_review(repository: Repository, days: int = 7) -> ContentReport:
    """Сводит Market Pulse и текущие проверенные решения без внешних чисел."""
    pulse = market_pulse(repository, days)
    decisions = repository.latest_decisions(limit=100)
    return ContentReport(
        kind="weekly_review",
        period_from=pulse.period_from,
        period_to=pulse.period_to,
        sample_size=pulse.sample_size,
        facts={**pulse.facts, "publishable_decisions": len(decisions)},
        provenance=[
            *pulse.provenance,
            *(f"{item.source}:{item.source_listing_id}" for item, _decision in decisions),
        ],
        template_version="weekly-review/v1",
    )


def deal_analysis(repository: Repository) -> ContentReport:
    """Выбирает одно текущее решение и публикует только его сохранённые факты."""
    now = datetime.now(UTC)
    decisions = repository.latest_decisions(limit=1)
    if not decisions:
        return ContentReport(
            kind="deal_analysis",
            period_from=now,
            period_to=now,
            sample_size=0,
            facts={"status": "no_current_publishable_decision"},
            provenance=[],
            template_version="deal-analysis/v1",
        )
    listing, decision = decisions[0]
    return ContentReport(
        kind="deal_analysis",
        period_from=listing.observed_at,
        period_to=now,
        sample_size=1,
        facts={
            "vehicle": " ".join(
                part for part in (listing.make, listing.model, str(listing.year or "")) if part
            ),
            "action": decision.action.value,
            "confidence_percent": str(decision.confidence * Decimal(100)),
        },
        provenance=[f"{listing.source}:{listing.source_listing_id}:{decision.decision_id}"],
        template_version="deal-analysis/v1",
    )


def audience_poll() -> dict[str, object]:
    """Детерминированный Telegram poll с CTA; числовых рыночных утверждений не содержит."""
    return {
        "question": "Which UAE used-car segment should we analyse next?",
        "options": ["SUV", "Sedan", "Sports car", "Budget car"],
        "cta": "/find",
        "template_version": "audience-poll/v1",
    }

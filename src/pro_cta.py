"""Воспроизводимые англоязычные CTA для конверсии Free-публикаций в Pro."""

from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import urlparse

from src.domain.ids import canonical_hash


@dataclass(frozen=True, slots=True)
class ProCta:
    """Сохранённый вариант текста и кнопки платной подписки."""

    variant_id: str
    text: str
    button_label: str
    fingerprint: str
    template_version: str = "pro-cta/v1"


_VARIANTS: tuple[tuple[str, str], ...] = (
    (
        "See the numbers this teaser leaves out — unlock the full Pro breakdown.",
        "Unlock full analysis",
    ),
    (
        "The asking price is only the headline. Pro shows the complete deal math.",
        "See the deal math",
    ),
    (
        "Want the verified market range behind this car? It is waiting in Pro.",
        "View verified market",
    ),
    (
        "Know the ceiling before you negotiate. Open the Pro purchase-price analysis.",
        "Reveal max purchase",
    ),
    (
        "A promising car still needs disciplined numbers. Get the Pro assessment.",
        "Open Pro assessment",
    ),
    (
        "Turn a market alert into an informed next step with the full Pro report.",
        "Get the full report",
    ),
    (
        "The photo gets attention. The verified numbers decide the opportunity.",
        "Unlock verified numbers",
    ),
    (
        "Before you message the seller, see costs, reserves and risk flags in Pro.",
        "Check costs and risks",
    ),
    (
        "This is the preview. The evidence, calculations and source are inside Pro.",
        "Open the evidence",
    ),
    (
        "Good buying starts with a clear limit. Discover the calculated ceiling.",
        "Find the buying limit",
    ),
    ("See how this car compares with current verified UAE listings.", "Compare in Pro"),
    (
        "Do not judge a deal by its price tag alone. Unlock the complete analysis.",
        "Analyse this opportunity",
    ),
    ("The market context changes everything. Get the verified Pro view.", "See market context"),
    ("One tap separates the teaser from the full acquisition picture.", "Unlock acquisition view"),
    (
        "Curious what remains after costs and reserves? Check the Pro calculation.",
        "View full calculation",
    ),
    (
        "A lower asking price is not enough. Pro shows whether the numbers hold up.",
        "Test the numbers",
    ),
    ("Make the next call with evidence, not guesswork. Open the Pro card.", "Open Pro card"),
    ("The opportunity is in the details: market, costs, return and risks.", "Reveal the details"),
    ("See the verified comparables used to evaluate this vehicle.", "View comparables"),
    ("Get the complete picture before this car reaches your shortlist.", "Complete the picture"),
    ("The teaser spots the car. Pro helps decide whether it deserves action.", "Decide with Pro"),
    ("Unlock the calculation designed for buyers, not browsers.", "Open buyer analysis"),
    ("Price is visible everywhere. A disciplined purchase limit is not.", "Reveal purchase limit"),
    ("Go beyond the listing and inspect the verified market evidence.", "Inspect market evidence"),
    ("See what the public card cannot show: the full Pro decision trail.", "Unlock decision trail"),
    (
        "Your shortlist deserves more than a headline. Add the complete analysis.",
        "Upgrade the shortlist",
    ),
    (
        "Check the downside before chasing the upside. Pro includes the risk view.",
        "Review the risk view",
    ),
    (
        "From interesting car to informed decision — unlock the missing numbers.",
        "Unlock missing numbers",
    ),
    ("The next negotiation starts with knowing what not to overpay.", "Set your price ceiling"),
    (
        "See why this vehicle appeared and what the verified data says next.",
        "Discover why it matters",
    ),
)


def pro_cta_count() -> int:
    """Возвращает размер утверждённого пула."""
    return len(_VARIANTS)


def pro_cta_for_index(index: int) -> ProCta:
    """Возвращает вариант по циклическому индексу."""
    normalized = index % len(_VARIANTS)
    text, button_label = _VARIANTS[normalized]
    variant_id = f"cta-{normalized + 1:02d}"
    fingerprint = canonical_hash(
        "pro-cta-fingerprint/v1",
        {"variant_id": variant_id, "text": text, "button_label": button_label},
    )
    return ProCta(
        variant_id=variant_id,
        text=text,
        button_label=button_label,
        fingerprint=fingerprint,
    )


def validated_subscription_url(value: str) -> str | None:
    """Принимает только прямую HTTPS-ссылку Telegram без credentials."""
    if not value or len(value) > 512:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"t.me", "telegram.me"}:
        return None
    if parsed.username or parsed.password or not parsed.path.strip("/"):
        return None
    return value


def append_pro_cta(message: str, cta: ProCta) -> str:
    """Добавляет безопасный CTA к HTML-сообщению Telegram."""
    return f"{message}\n\n⭐ <b>Go Pro</b>\n{html.escape(cta.text)}"

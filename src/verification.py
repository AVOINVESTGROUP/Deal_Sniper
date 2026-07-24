"""Проверка цены кандидата по актуальной странице объявления перед доставкой."""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.domain.models import MIN_VALID_LISTING_PRICE_AED, ListingSnapshot

MAX_DETAIL_PRICE_GAP = Decimal("0.03")


@dataclass(frozen=True, slots=True)
class PriceVerification:
    """Результат fail-closed проверки актуальной цены источника."""

    verified: bool
    detail_price_aed: Decimal | None
    reason: str


async def verify_listing_price(
    listing: ListingSnapshot,
    timeout_seconds: float = 30,
) -> PriceVerification:
    """Подтверждает цену по JSON-LD detail page; при сомнении запрещает доставку."""
    if listing.price_aed < MIN_VALID_LISTING_PRICE_AED:
        return PriceVerification(False, None, "Цена ниже минимального порога проверки")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(str(listing.url))
            response.raise_for_status()
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
        return PriceVerification(False, None, f"Detail page недоступна: {type(error).__name__}")

    prices = extract_detail_prices(response.text)
    if not prices:
        return PriceVerification(False, None, "Источник не подтвердил положительную цену AED")
    detail_price = min(prices, key=lambda value: abs(value - listing.price_aed))
    relative_gap = abs(detail_price - listing.price_aed) / max(detail_price, listing.price_aed)
    if relative_gap > MAX_DETAIL_PRICE_GAP:
        return PriceVerification(
            False,
            detail_price,
            f"Цена detail page отличается на {relative_gap:.1%}",
        )
    return PriceVerification(True, detail_price, "Цена подтверждена detail page")


def extract_detail_prices(html: str) -> list[Decimal]:
    """Извлекает только положительные AED offers из структурированных данных страницы."""
    soup = BeautifulSoup(html, "html.parser")
    prices: set[Decimal] = set()
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            document = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        for offer in _offers(document):
            if str(offer.get("priceCurrency", "")).upper() != "AED":
                continue
            try:
                price = Decimal(str(offer.get("price")))
            except (InvalidOperation, TypeError):
                continue
            if price >= MIN_VALID_LISTING_PRICE_AED:
                prices.add(price)
    return sorted(prices)


def _offers(value: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(value, dict):
        offers = value.get("offers")
        if isinstance(offers, dict):
            results.append(offers)
        elif isinstance(offers, list):
            results.extend(item for item in offers if isinstance(item, dict))
        for child in value.values():
            results.extend(_offers(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_offers(child))
    return results

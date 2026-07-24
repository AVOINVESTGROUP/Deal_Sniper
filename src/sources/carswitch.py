"""Получение объявлений CarSwitch из JSON-LD страницы поиска."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from src.domain.models import ListingSnapshot, SellerType
from src.sources.dubicars import SourceError

logger = logging.getLogger(__name__)


class CarSwitchSource:
    """Асинхронный адаптер страниц поиска CarSwitch."""

    def __init__(self, url_template: str, pages: int = 3, timeout_seconds: float = 30) -> None:
        self.url_template = url_template
        self.pages = pages
        self.timeout_seconds = timeout_seconds

    async def fetch(self) -> list[ListingSnapshot]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
        }
        listings: dict[str, ListingSnapshot] = {}
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers=headers,
        ) as client:
            for page in range(1, self.pages + 1):
                html = await self._get_with_retry(client, self.url_template.format(page=page))
                for listing in parse_carswitch_page(html):
                    listings[listing.source_listing_id] = listing
        if not listings:
            raise SourceError("CarSwitch не вернул распознаваемых объявлений")
        return list(listings.values())

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                last_error = error
                retryable = not isinstance(error, httpx.HTTPStatusError) or (
                    error.response.status_code in {408, 429, 500, 502, 503, 504}
                )
                if not retryable or attempt == 2:
                    break
                await asyncio.sleep(2**attempt)
        raise SourceError(f"Не удалось получить {url}: {last_error}") from last_error


def parse_carswitch_page(html: str) -> list[ListingSnapshot]:
    """Преобразует CarSwitch ItemList JSON-LD в снимки."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            document = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict) and document.get("@type") == "ItemList":
            return _parse_elements(document.get("itemListElement", []))
    raise SourceError("В странице CarSwitch отсутствует ItemList JSON-LD")


def _parse_elements(elements: Any) -> list[ListingSnapshot]:
    results: list[ListingSnapshot] = []
    if not isinstance(elements, list):
        return results
    for element in elements:
        try:
            item = element["mainEntity"]
            offer = item["offers"]
            url = str(item["url"])
            price = Decimal(str(offer["price"]))
            if offer.get("priceCurrency") != "AED" or price <= 0:
                continue
            mileage = item.get("mileageFromOdometer", {}).get("value")
            images = item.get("image", [])
            if isinstance(images, str):
                images = [images]
            results.append(
                ListingSnapshot(
                    source="carswitch",
                    source_listing_id=urlparse(url).path.rstrip("/").split("/")[-1],
                    url=HttpUrl(url),
                    title=str(item["name"]),
                    price_aed=price,
                    observed_at=datetime.now(UTC),
                    make=str(item.get("brand", {}).get("name") or "") or None,
                    model=str(item.get("model") or "") or None,
                    year=int(item["vehicleModelDate"]),
                    mileage_km=int(mileage) if mileage is not None else None,
                    location="Dubai",
                    seller_type=SellerType.CERTIFIED,
                    description=str(item.get("description", "")),
                    image_urls=[HttpUrl(str(image)) for image in images if image],
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            logger.warning("Пропущена некорректная запись CarSwitch JSON-LD", exc_info=True)
    return results

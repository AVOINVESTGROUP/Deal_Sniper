"""Получение объявлений Cars24 UAE из серверного состояния страницы поиска."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from src.domain.models import ListingSnapshot, SellerType
from src.sources.dubicars import SourceError

logger = logging.getLogger(__name__)
STATE_MARKER = "window.__PRELOADED_STATE__ ="
IMAGE_BASE_URL = "https://media-ae.cars24.com/"


class Cars24Source:
    """Асинхронный адаптер каталога сертифицированных автомобилей Cars24 UAE."""

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
                for listing in parse_cars24_page(html):
                    listings[listing.source_listing_id] = listing
        if not listings:
            raise SourceError("Cars24 не вернул распознаваемых объявлений")
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


def parse_cars24_page(html: str) -> list[ListingSnapshot]:
    """Преобразует `window.__PRELOADED_STATE__` Cars24 в снимки объявлений."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        if STATE_MARKER not in raw:
            continue
        payload = raw.split(STATE_MARKER, maxsplit=1)[1].strip().rstrip(";")
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as error:
            raise SourceError("Cars24 вернул некорректное состояние каталога") from error
        content = document.get("carListing", {}).get("content", [])
        return _parse_cars(content)
    raise SourceError("В странице Cars24 отсутствует состояние каталога")


def _parse_cars(items: Any) -> list[ListingSnapshot]:
    results: list[ListingSnapshot] = []
    if not isinstance(items, list):
        return results
    for item in items:
        try:
            if not item.get("listingActive", True) or item.get("booked", False):
                continue
            listing_id = str(item["appointmentId"])
            price = Decimal(str(item["price"]))
            if price <= 0:
                continue
            make = str(item["make"]).strip().title()
            model = str(item["model"]).strip().title()
            year = int(item["year"])
            variant = str(item.get("variant") or "").strip()
            title = " ".join(part for part in (str(year), make, model, variant) if part)
            image_url = _image_url(item.get("mainImage"))
            results.append(
                ListingSnapshot(
                    source="cars24",
                    source_listing_id=listing_id,
                    url=HttpUrl(str(item["shareUrl"])),
                    title=title,
                    price_aed=price,
                    observed_at=datetime.now(UTC),
                    make=make,
                    model=model,
                    year=year,
                    mileage_km=int(item["odometerReading"]),
                    location=str(item.get("city") or "Dubai"),
                    seller_type=SellerType.CERTIFIED,
                    description="Сертифицированный автомобиль Cars24 UAE",
                    image_urls=[HttpUrl(image_url)] if image_url else [],
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            logger.warning("Пропущена некорректная запись Cars24", exc_info=True)
    return results


def _image_url(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return IMAGE_BASE_URL + path.lstrip("/")

"""Получение объявлений DubiCars из JSON-LD страницы поиска."""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from src.domain.models import MIN_VALID_LISTING_PRICE_AED, ListingSnapshot, SellerType
from src.raw_storage import RawSnapshotArchive

logger = logging.getLogger(__name__)
LISTING_ID_PATTERN = re.compile(r"-(\d+)\.html$")


class SourceError(RuntimeError):
    """Источник не смог вернуть проверяемые данные."""


class DubiCarsSource:
    """Асинхронный адаптер страниц поиска DubiCars."""

    def __init__(
        self,
        url_template: str,
        pages: int = 3,
        timeout_seconds: float = 30,
        archive: RawSnapshotArchive | None = None,
        aed_to_usd_rate: Decimal = Decimal("3.6725"),
    ) -> None:
        self.url_template = url_template
        self.pages = pages
        self.timeout_seconds = timeout_seconds
        self.archive = archive
        self.aed_to_usd_rate = aed_to_usd_rate

    async def fetch(self) -> list[ListingSnapshot]:
        """Загружает несколько страниц с ограниченными повторами."""
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
                for item in parse_search_page(html, self.aed_to_usd_rate):
                    listings[item.source_listing_id] = item
        if not listings:
            raise SourceError("DubiCars не вернул распознаваемых объявлений")
        return list(listings.values())

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        """Повторяет только сетевые ошибки и временные HTTP-ответы."""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url)
                response.raise_for_status()
                if self.archive is not None:
                    await self.archive.save(
                        "dubicars",
                        str(response.url),
                        response.headers.get("content-type", "text/html"),
                        response.content,
                    )
                return response.text
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code in {408, 429, 500, 502, 503, 504}
                )
                if not retryable or attempt == 2:
                    break
                await asyncio.sleep(2**attempt)
        raise SourceError(f"Не удалось получить {url}: {last_error}") from last_error


def parse_search_page(
    html: str,
    aed_to_usd_rate: Decimal = Decimal("3.6725"),
) -> list[ListingSnapshot]:
    """Преобразует ItemList JSON-LD в доменные снимки."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        try:
            document = json.loads(raw)
        except json.JSONDecodeError:
            continue
        graph = document.get("@graph", []) if isinstance(document, dict) else []
        for node in graph:
            if isinstance(node, dict) and node.get("@type") == "ItemList":
                return _parse_item_list(node.get("itemListElement", []), aed_to_usd_rate)
    raise SourceError("В странице отсутствует ItemList JSON-LD")


def _parse_item_list(elements: Any, aed_to_usd_rate: Decimal) -> list[ListingSnapshot]:
    results: list[ListingSnapshot] = []
    if not isinstance(elements, list):
        return results
    for element in elements:
        try:
            item = element["item"]
            if str(item.get("itemCondition", "")).endswith("NewCondition"):
                continue
            offer = item["offers"]
            url = str(item["url"])
            price = Decimal(str(offer["price"]))
            currency = offer.get("priceCurrency")
            if currency == "USD":
                price *= aed_to_usd_rate
            elif currency != "AED":
                continue
            if price < MIN_VALID_LISTING_PRICE_AED:
                continue
            listing_id = _source_listing_id(url)
            make = _name_from_schema_id(item.get("brand"))
            model = _name_from_schema_id(item.get("model"))
            mileage = item.get("mileageFromOdometer", {}).get("value")
            image = item.get("image")
            results.append(
                ListingSnapshot(
                    source="dubicars",
                    source_listing_id=listing_id,
                    url=HttpUrl(url),
                    title=str(item["name"]),
                    price_aed=price,
                    observed_at=datetime.now(UTC),
                    make=make,
                    model=model,
                    trim=str(item.get("vehicleConfiguration") or "").strip() or None,
                    year=int(item["vehicleModelDate"]),
                    mileage_km=int(mileage) if mileage is not None else None,
                    body_type=str(item.get("bodyType") or "").strip() or None,
                    transmission=str(item.get("vehicleTransmission") or "").strip() or None,
                    fuel_type=str(item.get("fuelType") or "").strip() or None,
                    seller_type=SellerType.DEALER,
                    image_urls=[HttpUrl(str(image))] if image else [],
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            logger.warning("Пропущена некорректная запись JSON-LD", exc_info=True)
    return results


def _source_listing_id(url: str) -> str:
    match = LISTING_ID_PATTERN.search(urlparse(url).path)
    if match:
        return match.group(1)
    return urlparse(url).path.strip("/").replace("/", "-")


def _name_from_schema_id(value: Any) -> str | None:
    if not isinstance(value, dict) or "@id" not in value:
        return None
    path = urlparse(str(value["@id"])).path.rstrip("/")
    slug = path.split("/")[-1].split("#", maxsplit=1)[0]
    return slug.replace("-", " ").title() or None

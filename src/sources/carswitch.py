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

from src.domain.models import MIN_VALID_LISTING_PRICE_AED, ListingSnapshot, SellerType
from src.raw_storage import RawSnapshotArchive
from src.sources.dubicars import SourceError

logger = logging.getLogger(__name__)
SEMANTIC_EMPTY_RESPONSE = "semantic_empty_response"
MAX_FETCH_ATTEMPTS = 3
ALLOWED_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


class CarSwitchSemanticResponseError(SourceError):
    """HTTP-ответ получен, но не содержит проверяемого каталога CarSwitch."""


class CarSwitchSource:
    """Асинхронный адаптер страниц поиска CarSwitch."""

    def __init__(
        self,
        url_template: str,
        pages: int = 3,
        timeout_seconds: float = 30,
        archive: RawSnapshotArchive | None = None,
    ) -> None:
        self.url_template = url_template
        self.pages = pages
        self.timeout_seconds = timeout_seconds
        self.archive = archive

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
                page_listings = await self._get_page_with_retry(
                    client,
                    self.url_template.format(page=page),
                )
                for listing in page_listings:
                    listings[listing.source_listing_id] = listing
        if not listings:
            raise SourceError("CarSwitch не вернул распознаваемых объявлений")
        return list(listings.values())

    async def _get_page_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> list[ListingSnapshot]:
        """Архивирует и проверяет HTTP-ответ внутри единого bounded retry."""
        last_error: Exception | None = None
        for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
            try:
                response = await client.get(url)
                response.raise_for_status()
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
                last_error = error
                retryable = not isinstance(error, httpx.HTTPStatusError) or (
                    error.response.status_code in {408, 429, 500, 502, 503, 504}
                )
                if not retryable or attempt == MAX_FETCH_ATTEMPTS:
                    category = (
                        "temporary_http_error"
                        if retryable
                        else "permanent_http_error"
                    )
                    raise SourceError(
                        f"Не удалось получить {url}: {error}",
                        category=category,
                        attempts=attempt,
                    ) from error
            else:
                content_type = response.headers.get("content-type", "")
                if self.archive is not None:
                    await self.archive.save(
                        "carswitch",
                        str(response.url),
                        content_type or "application/octet-stream",
                        response.content,
                        attempt_number=attempt,
                    )
                try:
                    if not response.content.strip():
                        raise CarSwitchSemanticResponseError(
                            "CarSwitch вернул пустой HTTP 200"
                        )
                    media_type = content_type.split(";", 1)[0].strip().casefold()
                    if media_type not in ALLOWED_HTML_CONTENT_TYPES:
                        rendered_content_type = media_type or "missing"
                        raise CarSwitchSemanticResponseError(
                            "CarSwitch вернул неподходящий content type: "
                            f"{rendered_content_type}"
                        )
                    return parse_carswitch_page(response.text)
                except CarSwitchSemanticResponseError as error:
                    last_error = error
                    if attempt == MAX_FETCH_ATTEMPTS:
                        raise SourceError(
                            f"CarSwitch исчерпал retry после семантически пустого ответа: {error}",
                            category=SEMANTIC_EMPTY_RESPONSE,
                            attempts=attempt,
                        ) from error

            await asyncio.sleep(2 ** (attempt - 1))

        raise SourceError(
            f"Не удалось получить {url}: {last_error}",
            category=SEMANTIC_EMPTY_RESPONSE,
            attempts=MAX_FETCH_ATTEMPTS,
        ) from last_error


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
    raise CarSwitchSemanticResponseError(
        "В странице CarSwitch отсутствует ItemList JSON-LD"
    )


def _parse_elements(elements: Any) -> list[ListingSnapshot]:
    results: list[ListingSnapshot] = []
    if not isinstance(elements, list):
        return results
    for element in elements:
        try:
            item = element["mainEntity"]
            if not isinstance(item, dict):
                continue
            offer = item.get("offers")
            if not isinstance(offer, dict):
                continue
            url = str(item["url"])
            price = Decimal(str(offer["price"]))
            offer_text = " ".join(
                str(offer.get(field, "")).casefold()
                for field in ("unitText", "priceType", "name", "description")
            )
            non_purchase_markers = {
                "month",
                "monthly",
                "installment",
                "finance",
                "downpayment",
                "request",
                "contact",
            }
            if (
                offer.get("priceCurrency") != "AED"
                or price < MIN_VALID_LISTING_PRICE_AED
                or any(marker in offer_text for marker in non_purchase_markers)
            ):
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
                    trim=str(item.get("vehicleConfiguration") or "").strip() or None,
                    year=int(item["vehicleModelDate"]),
                    mileage_km=int(mileage) if mileage is not None else None,
                    body_type=str(item.get("bodyType") or "").strip() or None,
                    transmission=str(item.get("vehicleTransmission") or "").strip() or None,
                    fuel_type=str(item.get("fuelType") or "").strip() or None,
                    location="Dubai",
                    seller_type=SellerType.CERTIFIED,
                    description=str(item.get("description", "")),
                    image_urls=[HttpUrl(str(image)) for image in images if image],
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            logger.warning("Пропущена некорректная запись CarSwitch JSON-LD", exc_info=True)
    return results

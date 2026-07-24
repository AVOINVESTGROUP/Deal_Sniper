"""Получение объявлений OpenSooq UAE из серверного состояния каталога."""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from src.domain.models import ListingSnapshot, SellerType
from src.raw_storage import RawSnapshotArchive
from src.sources.dubicars import SourceError

logger = logging.getLogger(__name__)
YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
IMAGE_BASE_URL = "https://opensooq-imagesv2.os-cdn.com/previews/2048x0/"


class OpenSooqSource:
    """Асинхронный адаптер свежих объявлений OpenSooq UAE."""

    def __init__(
        self,
        url_template: str,
        pages: int = 5,
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
                url = self.url_template.format(page=page)
                html = await self._get_with_retry(client, url)
                for listing in parse_opensooq_page(html):
                    listings[listing.source_listing_id] = listing
        if not listings:
            raise SourceError("OpenSooq не вернул распознаваемых объявлений")
        return list(listings.values())

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url)
                response.raise_for_status()
                if self.archive is not None:
                    await self.archive.save(
                        "opensooq",
                        str(response.url),
                        response.headers.get("content-type", "text/html"),
                        response.content,
                    )
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


def parse_opensooq_page(html: str) -> list[ListingSnapshot]:
    """Преобразует `__NEXT_DATA__` OpenSooq в доменные снимки."""
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None:
        raise SourceError("В странице OpenSooq отсутствует состояние каталога")
    try:
        document = json.loads(script.string or script.get_text())
        items = document["props"]["pageProps"]["serpApiResponse"]["listings"]["items"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise SourceError("OpenSooq вернул некорректное состояние каталога") from error
    return _parse_items(items)


def _parse_items(items: Any) -> list[ListingSnapshot]:
    results: list[ListingSnapshot] = []
    if not isinstance(items, list):
        return results
    for item in items:
        try:
            if not item.get("is_active", True):
                continue
            price = Decimal(_digits(item["price_amount"]))
            if item.get("price_currency_iso") != "AED" or price <= 0:
                continue
            cps = [str(value).strip() for value in item.get("cps", [])]
            if len(cps) < 4 or cps[0].casefold() != "used":
                continue
            year_index = next(
                index
                for index, value in enumerate(cps)
                if YEAR_PATTERN.fullmatch(value.replace(",", ""))
            )
            if year_index < 3:
                continue
            make = cps[1]
            model = cps[2]
            trim = " ".join(cps[3:year_index]).strip() or None
            year = int(cps[year_index].replace(",", ""))
            mileage = int(_digits(str(item["kilometers_Cars_value_i"])))
            listing_id = str(item["id"])
            post_url = str(item.get("post_url") or f"/search/{listing_id}")
            image_uri = str(item.get("image_uri") or "").strip()
            image_urls = [HttpUrl(f"{IMAGE_BASE_URL}{image_uri}.webp")] if image_uri else []
            body_type = cps[year_index + 2] if len(cps) > year_index + 2 else None
            description = str(item.get("masked_description") or "")
            specification = _specification(item.get("starCps"))
            seller_type = (
                SellerType.DEALER
                if str(item.get("user_target_type", "")).casefold() not in {"", "free"}
                else SellerType.PRIVATE
            )
            results.append(
                ListingSnapshot(
                    source="opensooq",
                    source_listing_id=listing_id,
                    url=HttpUrl(f"https://ae.opensooq.com/en{post_url}"),
                    title=str(item["title"]),
                    price_aed=price,
                    observed_at=datetime.now(UTC),
                    make=make,
                    model=model,
                    trim=trim,
                    year=year,
                    mileage_km=mileage,
                    specification=specification,
                    body_type=body_type,
                    location=str(item.get("city_label") or "") or None,
                    seller_type=seller_type,
                    description=description,
                    image_urls=image_urls,
                )
            )
        except (KeyError, StopIteration, TypeError, ValueError, InvalidOperation):
            logger.warning("Пропущена некорректная запись OpenSooq", exc_info=True)
    return results


def _digits(value: str) -> str:
    result = "".join(character for character in value if character.isdigit())
    if not result:
        raise ValueError("Числовое значение отсутствует")
    return result


def _specification(values: Any) -> str | None:
    if not isinstance(values, list):
        return None
    for value in values:
        if not isinstance(value, dict):
            continue
        label = str(value.get("label") or "").strip()
        if label.casefold().endswith("specs"):
            return label
    return None

"""Динамический HTTPS JSON feed с обязательной проверкой фиксированных цен."""

import asyncio
import ipaddress
import json
import socket
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import HttpUrl

from src.domain.models import MIN_VALID_LISTING_PRICE_AED, ListingSnapshot
from src.raw_storage import RawSnapshotArchive
from src.sources.dubicars import SourceError


class JsonFeedSource:
    """Адаптер публичного JSON feed без секретов и скрытого mock fallback."""

    def __init__(
        self,
        name: str,
        url: str,
        timeout_seconds: float = 30,
        archive: RawSnapshotArchive | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.archive = archive

    async def fetch(self) -> list[ListingSnapshot]:
        await validate_public_https_url(self.url)
        headers = {"User-Agent": "DubaiDealSniper/1.0 (+structured-feed)"}
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=self.timeout_seconds, headers=headers
        ) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            await validate_public_https_url(str(response.url))
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type.casefold():
                raise SourceError("Источник не вернул JSON content type")
            if len(response.content) > 10_000_000:
                raise SourceError("JSON feed превышает допустимые 10 MB")
            if self.archive is not None:
                await self.archive.save(
                    self.name, str(response.url), content_type, response.content
                )
            try:
                payload = response.json()
            except json.JSONDecodeError as error:
                raise SourceError("Источник вернул некорректный JSON") from error
        listings = parse_json_feed(self.name, payload)
        if not listings:
            raise SourceError(
                "Не найдено объявлений с ID, URL, названием и фиксированной ценой от 5,000 AED"
            )
        return listings


async def validate_public_https_url(url: str) -> None:
    """Запрещает локальные адреса и приватные сети для защиты server-side fetch."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceError("Разрешён только публичный HTTPS URL без credentials")
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as error:
        raise SourceError("Не удалось определить адрес источника") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise SourceError("Локальные и приватные адреса запрещены")


def parse_json_feed(name: str, payload: Any) -> list[ListingSnapshot]:
    """Поддерживает массив либо стандартные контейнеры items/listings/results/data."""
    items = _items(payload)
    results: dict[str, ListingSnapshot] = {}
    for raw in items[:2_000]:
        if not isinstance(raw, dict):
            continue
        listing = _parse_item(name, raw)
        if listing is not None:
            results[listing.source_listing_id] = listing
    return list(results.values())


def _items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("items", "listings", "results", "data", "vehicles", "cars"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _items(value)
            if nested:
                return nested
    return []


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _price(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        value = _first(value, "amount", "value", "aed")
    text = str(value or "").casefold()
    if not text or any(marker in text for marker in ("request", "contact", "call", "poa")):
        return None
    cleaned = "".join(character for character in text if character.isdigit() or character == ".")
    try:
        price = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
    return price if price >= MIN_VALID_LISTING_PRICE_AED else None


def _integer(value: Any) -> int | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return int(digits) if digits else None


def _parse_item(name: str, raw: dict[str, Any]) -> ListingSnapshot | None:
    source_id = _first(raw, "id", "listing_id", "listingId", "stock_id", "stockId")
    title = _first(raw, "title", "name", "headline")
    url = _first(raw, "url", "listing_url", "listingUrl", "link")
    price = _price(_first(raw, "price_aed", "price", "amount"))
    make = _first(raw, "make", "brand", "manufacturer")
    model = _first(raw, "model", "model_name", "modelName")
    year = _integer(_first(raw, "year", "model_year", "modelYear"))
    if not source_id or not title or not url or price is None:
        return None
    if not (make and model) and year is None:
        return None
    images = _first(raw, "image_urls", "images", "photos") or []
    if isinstance(images, str):
        images = [images]
    if not isinstance(images, list):
        images = []
    image_urls: list[HttpUrl] = []
    for image in images[:20]:
        candidate = image.get("url") if isinstance(image, dict) else image
        try:
            image_urls.append(HttpUrl(str(candidate)))
        except ValueError:
            continue
    observed = datetime.now(UTC)
    try:
        return ListingSnapshot(
            source=name,
            source_listing_id=str(source_id),
            url=HttpUrl(str(url)),
            title=str(title).strip(),
            price_aed=price,
            observed_at=observed,
            fetched_at=observed,
            make=str(make).strip() if make else None,
            model=str(model).strip() if model else None,
            year=year,
            mileage_km=_integer(_first(raw, "mileage_km", "mileage", "odometer")),
            trim=str(_first(raw, "trim", "variant") or "").strip() or None,
            specification=str(_first(raw, "specification", "specs") or "").strip() or None,
            location=str(_first(raw, "location", "city") or "").strip() or None,
            description=str(_first(raw, "description", "summary") or "").strip(),
            image_urls=image_urls,
        )
    except ValueError:
        return None

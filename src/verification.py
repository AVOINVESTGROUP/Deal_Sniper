"""Source-bound detail verification до нормализации и рыночного расчёта."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.domain.ids import evidence_revision_id, money_value, verification_key
from src.domain.models import (
    MIN_VALID_LISTING_PRICE_AED,
    FreshnessStatus,
    ListingSnapshot,
    VerificationEvidence,
    VerificationStatus,
)

MAX_DETAIL_PRICE_GAP = Decimal("0.03")
DEFAULT_VERIFICATION_TTL = timedelta(minutes=30)
EXTRACTOR_VERSION = "detail-jsonld/v2"


class TemporaryVerificationError(RuntimeError):
    """Ошибка, при которой Cloud Tasks обязан повторить запрос."""


@dataclass(frozen=True, slots=True)
class PriceVerification:
    """Результат source-bound проверки detail page."""

    status: VerificationStatus
    detail_price_aed: Decimal | None
    reason: str
    checksum_sha256: str | None = None
    currency: str | None = None
    extractor_version: str = EXTRACTOR_VERSION
    latency_ms: int | None = None

    @property
    def verified(self) -> bool:
        return self.status is VerificationStatus.VERIFIED

    @property
    def retriable(self) -> bool:
        return self.status is VerificationStatus.TEMPORARY_ERROR


async def verify_listing_price(
    listing: ListingSnapshot,
    timeout_seconds: float = 30,
) -> PriceVerification:
    """Подтверждает цену только offer, привязанным к конкретному listing."""
    if listing.price_aed < MIN_VALID_LISTING_PRICE_AED:
        return PriceVerification(
            VerificationStatus.PERMANENT_INVALID,
            None,
            "Цена ниже минимального порога проверки",
        )
    if not listing.make or not listing.model or listing.year is None:
        return PriceVerification(
            VerificationStatus.PERMANENT_INVALID,
            None,
            "Для проверки обязательны make, model и year",
        )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
    }
    started = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(str(listing.url))
    except (httpx.TimeoutException, httpx.NetworkError) as error:
        return PriceVerification(
            VerificationStatus.TEMPORARY_ERROR,
            None,
            f"Detail page временно недоступна: {type(error).__name__}",
        )
    latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    checksum = hashlib.sha256(response.content).hexdigest()
    if response.status_code == 429 or response.status_code >= 500:
        return PriceVerification(
            VerificationStatus.TEMPORARY_ERROR,
            None,
            f"Временный HTTP status {response.status_code}",
            checksum_sha256=checksum,
            latency_ms=latency_ms,
        )
    if response.status_code >= 400:
        return PriceVerification(
            VerificationStatus.PERMANENT_INVALID,
            None,
            f"Постоянный HTTP status {response.status_code}",
            checksum_sha256=checksum,
            latency_ms=latency_ms,
        )

    prices = extract_detail_prices(response.text, listing)
    if not prices:
        return PriceVerification(
            VerificationStatus.PERMANENT_INVALID,
            None,
            "Конкретный listing не подтвердил фиксированную цену AED",
            checksum_sha256=checksum,
            latency_ms=latency_ms,
        )
    detail_price = min(prices, key=lambda value: abs(value - listing.price_aed))
    relative_gap = abs(detail_price - listing.price_aed) / max(detail_price, listing.price_aed)
    if relative_gap > MAX_DETAIL_PRICE_GAP:
        return PriceVerification(
            VerificationStatus.PERMANENT_INVALID,
            detail_price,
            f"Цена detail page отличается на {relative_gap:.1%}",
            checksum_sha256=checksum,
            currency="AED",
            latency_ms=latency_ms,
        )
    return PriceVerification(
        VerificationStatus.VERIFIED,
        detail_price,
        "Цена подтверждена detail page",
        checksum_sha256=checksum,
        currency="AED",
        latency_ms=latency_ms,
    )


def build_evidence(
    listing: ListingSnapshot,
    content_hash: str,
    result: PriceVerification,
    *,
    now: datetime | None = None,
    previous: VerificationEvidence | None = None,
    ttl: timedelta = DEFAULT_VERIFICATION_TTL,
) -> VerificationEvidence:
    """Создаёт revision либо продлевает operational freshness прежней revision."""
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    listing_id = f"{listing.source}:{listing.source_listing_id}"
    key = verification_key(listing.source, listing_id, content_hash, result.extractor_version)
    semantic = {
        "verification_key": key,
        "listing_id": listing_id,
        "content_hash": content_hash,
        "status": result.status.value,
        "verified_price_aed": (
            money_value(result.detail_price_aed) if result.detail_price_aed is not None else None
        ),
        "currency": result.currency,
        "extractor_version": result.extractor_version,
        "rejection_reason": result.reason if not result.verified else None,
    }
    revision = evidence_revision_id(semantic)
    same_revision = previous is not None and previous.evidence_revision_id == revision
    if same_revision and previous is not None:
        created_at = previous.evidence_created_at
        attempts = previous.attempt_count + 1
    else:
        created_at = checked_at
        attempts = 1
    freshness = FreshnessStatus.ACTIVE if result.verified else FreshnessStatus.EXPIRED
    return VerificationEvidence(
        verification_key=key,
        evidence_revision_id=revision,
        listing_id=listing_id,
        content_hash=content_hash,
        source=listing.source,
        status=result.status,
        freshness_status=freshness,
        verified_price_aed=result.detail_price_aed,
        currency=result.currency,
        checksum_sha256=result.checksum_sha256,
        extractor_version=result.extractor_version,
        rejection_reason=None if result.verified else result.reason,
        evidence_created_at=created_at,
        last_checked_at=checked_at,
        valid_until=checked_at + ttl if result.verified else checked_at,
        attempt_count=attempts,
        latency_ms=result.latency_ms,
    )


def evidence_is_active(evidence: VerificationEvidence, now: datetime | None = None) -> bool:
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    return (
        evidence.status is VerificationStatus.VERIFIED
        and evidence.freshness_status is FreshnessStatus.ACTIVE
        and evidence.valid_until > reference
    )


def extract_detail_prices(html: str, listing: ListingSnapshot | None = None) -> list[Decimal]:
    """Извлекает AED offer только из JSON-LD узла конкретного автомобиля."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            document = json.loads(script.string or script.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        candidates.extend(_owned_offers(document))

    if listing is not None:
        bound = [(owner, offer) for owner, offer in candidates if _matches_listing(owner, listing)]
        if bound:
            candidates = bound
        else:
            vehicle_owners = {
                json.dumps(owner, ensure_ascii=False, sort_keys=True, default=str)
                for owner, _offer in candidates
                if _is_vehicle_node(owner)
            }
            if len(vehicle_owners) != 1:
                candidates = []

    prices: set[Decimal] = set()
    for _owner, offer in candidates:
        if str(offer.get("priceCurrency", "")).upper() != "AED":
            continue
        try:
            price = Decimal(str(offer.get("price")))
        except (InvalidOperation, TypeError):
            continue
        if price >= MIN_VALID_LISTING_PRICE_AED:
            prices.add(price)
    if listing is not None:
        prices.update(_embedded_listing_prices(soup, listing))
    return sorted(prices)


def _embedded_listing_prices(soup: BeautifulSoup, listing: ListingSnapshot) -> set[Decimal]:
    """Извлекает цену из owner object server state, строго связанного с source listing ID."""
    results: set[Decimal] = set()
    for script in soup.find_all("script"):
        raw = script.string or script.get_text()
        if listing.source_listing_id not in raw:
            continue
        payload = raw.strip()
        if "window.__PRELOADED_STATE__ =" in payload:
            payload = payload.split("window.__PRELOADED_STATE__ =", maxsplit=1)[1]
        payload = payload.rstrip(";")
        try:
            document = json.loads(payload)
        except json.JSONDecodeError:
            continue
        for owner in _find_listing_owners(document, listing.source_listing_id):
            for key in ("targetPrice", "cars24Price", "price", "salePrice"):
                value = owner.get(key)
                try:
                    price = Decimal(str(value))
                except (InvalidOperation, TypeError):
                    continue
                if price >= MIN_VALID_LISTING_PRICE_AED:
                    results.add(price)
            price_benefits = owner.get("priceBenefits")
            if isinstance(price_benefits, dict):
                for key in ("cars24Price", "price"):
                    try:
                        price = Decimal(str(price_benefits.get(key)))
                    except (InvalidOperation, TypeError):
                        continue
                    if price >= MIN_VALID_LISTING_PRICE_AED:
                        results.add(price)
    return results


def _find_listing_owners(value: Any, listing_id: str) -> list[dict[str, Any]]:
    owners: list[dict[str, Any]] = []
    if isinstance(value, dict):
        identity_values = {
            str(value.get(key, ""))
            for key in ("appointmentId", "listingId", "id", "sku", "productId")
        }
        if listing_id in identity_values:
            owners.append(value)
        for child in value.values():
            owners.extend(_find_listing_owners(child, listing_id))
    elif isinstance(value, list):
        for child in value:
            owners.extend(_find_listing_owners(child, listing_id))
    return owners


def _owned_offers(value: Any) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if isinstance(value, dict):
        offers = value.get("offers")
        if isinstance(offers, dict):
            results.append((value, offers))
        elif isinstance(offers, list):
            results.extend((value, item) for item in offers if isinstance(item, dict))
        for child in value.values():
            results.extend(_owned_offers(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_owned_offers(child))
    return results


def _matches_listing(owner: dict[str, Any], listing: ListingSnapshot) -> bool:
    identity = " ".join(
        str(owner.get(field, ""))
        for field in ("url", "@id", "sku", "productID", "name", "description")
    ).casefold()
    listing_id = listing.source_listing_id.casefold()
    path_tokens = [token for token in re.split(r"[/_.-]", str(listing.url).casefold()) if token]
    title_tokens = [token for token in re.split(r"\W+", listing.title.casefold()) if len(token) > 3]
    return bool(
        listing_id in identity
        or any(token in identity for token in path_tokens[-3:])
        or (title_tokens and sum(token in identity for token in title_tokens) >= 2)
    )


def _is_vehicle_node(owner: dict[str, Any]) -> bool:
    value = owner.get("@type")
    types = value if isinstance(value, list) else [value]
    return any(str(item).casefold() in {"vehicle", "car", "product"} for item in types)

"""Fail-closed клиент новостей авторынка Дубая с provenance."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Проверяемая ссылка на опубликованный материал."""

    title: str
    publisher: str
    url: str
    published_at: datetime


class DubaiAutoNewsClient:
    """Читает RSS, ограничивает свежесть и не генерирует отсутствующие данные."""

    def __init__(
        self,
        feed_url: str,
        timeout_seconds: float,
        max_age_days: int,
        limit: int,
    ) -> None:
        if urlparse(feed_url).scheme != "https":
            raise ValueError("AUTO_NEWS_RSS_URL должен использовать HTTPS")
        self.feed_url = feed_url
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max(1, max_age_days)
        self.limit = max(1, min(limit, 5))

    async def latest(self, now: datetime | None = None) -> list[NewsItem]:
        """Возвращает свежие уникальные материалы либо пустой список при ошибке."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "DubaiDealSniper/1.1"},
            ) as client:
                response = await client.get(self.feed_url)
                response.raise_for_status()
            return parse_news_feed(
                response.content,
                now=now or datetime.now(UTC),
                max_age_days=self.max_age_days,
                limit=self.limit,
            )
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as error:
            logger.warning("Новостная лента временно недоступна: %s", type(error).__name__)
            return []


def parse_news_feed(
    payload: bytes,
    *,
    now: datetime,
    max_age_days: int,
    limit: int,
) -> list[NewsItem]:
    """Разбирает RSS и отбрасывает старые, неполные и небезопасные записи."""
    root = ElementTree.fromstring(payload)
    cutoff = now.astimezone(UTC) - timedelta(days=max(1, max_age_days))
    items: list[NewsItem] = []
    seen: set[str] = set()
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        url = (node.findtext("link") or "").strip()
        published_raw = (node.findtext("pubDate") or "").strip()
        source = node.find("source")
        publisher = ((source.text if source is not None else "") or "").strip()
        normalized_title = title.casefold()
        has_location = "dubai" in normalized_title or "uae" in normalized_title
        has_automotive_topic = any(
            token in normalized_title
            for token in ("car", "vehicle", "automotive", "pre-owned", "used auto", "ev ")
        )
        if (
            not title
            or not publisher
            or not has_location
            or not has_automotive_topic
            or urlparse(url).scheme != "https"
        ):
            continue
        try:
            published_at = parsedate_to_datetime(published_raw).astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            continue
        if published_at < cutoff or published_at > now.astimezone(UTC) + timedelta(hours=1):
            continue
        fingerprint = " ".join(title.casefold().split())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        items.append(
            NewsItem(
                title=title,
                publisher=publisher,
                url=url,
                published_at=published_at,
            )
        )
    items.sort(key=lambda item: item.published_at, reverse=True)
    return items[: max(1, min(limit, 5))]


def format_news(items: list[NewsItem]) -> str:
    """Формирует компактный англоязычный ответ с источником и датой."""
    lines = ["<b>Dubai automotive news</b>", ""]
    for item in items:
        title = html.escape(item.title)
        publisher = html.escape(item.publisher)
        date = item.published_at.strftime("%d %b %Y")
        url = html.escape(item.url, quote=True)
        lines.extend(
            [
                f'• <a href="{url}">{title}</a>',
                f"  {publisher} · {date}",
                "",
            ]
        )
    lines.append("Headlines are sourced. Open the article for the full context.")
    return "\n".join(lines)

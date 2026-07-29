"""Fail-closed клиент новостей авторынка Дубая с provenance."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from src.domain.ids import canonical_hash

logger = logging.getLogger(__name__)

NEWS_AGGREGATOR_HOSTS = frozenset(
    {
        "news.google.com",
        "www.google.com",
        "news.yahoo.com",
    }
)


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Проверяемая ссылка на опубликованный материал."""

    title: str
    publisher: str
    url: str
    published_at: datetime
    summary: str = ""

    @property
    def fingerprint(self) -> str:
        """Стабильная идентичность статьи для защиты от повторной публикации."""
        return canonical_hash(
            "pro-news-item/v1",
            {
                "url": canonical_news_url(self.url),
                "publisher": self.publisher.casefold().strip(),
                "published_at": self.published_at.astimezone(UTC).date().isoformat(),
            },
        )


class DubaiAutoNewsClient:
    """Читает RSS, ограничивает свежесть и не генерирует отсутствующие данные."""

    def __init__(
        self,
        feed_url: str,
        timeout_seconds: float,
        max_age_days: int,
        limit: int,
        publisher_hint: str = "",
    ) -> None:
        if feed_url and urlparse(feed_url).scheme != "https":
            raise ValueError("AUTO_NEWS_RSS_URL должен использовать HTTPS")
        self.feed_url = feed_url
        self.timeout_seconds = timeout_seconds
        self.max_age_days = max(1, max_age_days)
        self.limit = max(1, min(limit, 5))
        self.publisher_hint = publisher_hint.strip()

    async def latest(self, now: datetime | None = None) -> list[NewsItem]:
        """Возвращает свежие уникальные материалы либо пустой список при ошибке."""
        if not self.feed_url:
            return []
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
                publisher_hint=self.publisher_hint,
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
    publisher_hint: str = "",
) -> list[NewsItem]:
    """Разбирает RSS/Atom и отбрасывает старые, неполные и нерелевантные записи."""
    root = ElementTree.fromstring(payload)
    cutoff = now.astimezone(UTC) - timedelta(days=max(1, max_age_days))
    items: list[NewsItem] = []
    seen: set[str] = set()
    nodes = [*root.findall(".//item"), *root.findall(".//{*}entry")]
    for node in nodes:
        is_atom = node.tag.endswith("entry")
        title = ((node.findtext("{*}title") if is_atom else node.findtext("title")) or "").strip()
        if is_atom:
            link = node.find("{*}link")
            url = ((link.get("href") if link is not None else "") or "").strip()
            published_raw = (
                node.findtext("{*}published") or node.findtext("{*}updated") or ""
            ).strip()
            publisher = (
                node.findtext("{*}source/{*}title")
                or node.findtext("{*}author/{*}name")
                or publisher_hint
            ).strip()
            summary_raw = node.findtext("{*}summary") or node.findtext("{*}content") or ""
        else:
            url = (node.findtext("link") or "").strip()
            published_raw = (node.findtext("pubDate") or "").strip()
            source = node.find("source")
            publisher = (
                ((source.text if source is not None else "") or "").strip()
                or publisher_hint
            )
            summary_raw = node.findtext("description") or ""
        summary = _plain_text(summary_raw)
        normalized_content = f"{title} {summary}".casefold()
        has_location = "dubai" in normalized_content or "uae" in normalized_content
        has_automotive_topic = any(
            token in normalized_content
            for token in (
                "car",
                "vehicle",
                "automotive",
                "pre-owned",
                "used auto",
                "electric vehicle",
                " ev ",
                "mobility",
            )
        )
        if (
            not title
            or not publisher
            or not has_location
            or not has_automotive_topic
            or not is_direct_publisher_url(url)
        ):
            continue
        published_at = _published_at(published_raw)
        if published_at is None:
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
                summary=summary[:2_000],
            )
        )
    items.sort(key=lambda item: item.published_at, reverse=True)
    return items[: max(1, min(limit, 5))]


def is_direct_publisher_url(url: str) -> bool:
    """Разрешает HTTPS-ссылку издателя и отбрасывает известные агрегаторы."""
    parsed = urlparse(url)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.hostname.casefold() not in NEWS_AGGREGATOR_HOSTS
    )


def _published_at(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _plain_text(value: str) -> str:
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def canonical_news_url(value: str) -> str:
    """Нормализует HTTPS URL, сохраняя значимую query-часть агрегаторов."""
    parsed = urlparse(value.strip())
    return parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=parsed.netloc.casefold(),
        fragment="",
    ).geturl()


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

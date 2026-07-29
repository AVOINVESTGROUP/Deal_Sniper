"""Контракты регулярных Pro-новостей и управляемого реестра лент R7.3."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from src.auth import Principal
from src.config import Settings
from src.domain.models import FreshnessStatus, NewsEvidence, NewsFeedConfiguration, OutboxState
from src.news import NewsItem, parse_news_feed
from src.pro_news import (
    PRO_NEWS_TEMPLATE_VERSION,
    format_pro_news_digest,
    preview_pro_news_publication,
    reconcile_pro_news_publication,
)
from src.storage import LocalRepository


class FakeContentDispatcher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


def pro_news_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_PRO_CHANNEL_ID", "-100777")
    monkeypatch.setenv("PRO_NEWS_ENABLED", "true")
    monkeypatch.setenv("PRO_NEWS_MAX_ITEMS", "2")
    monkeypatch.setenv("PRO_NEWS_MIN_INTERVAL_HOURS", "6")
    monkeypatch.setenv("PRO_NEWS_AI_SUMMARY_ENABLED", "false")
    monkeypatch.setenv("AUTO_NEWS_RSS_URL", "https://news.example/feed.xml")
    return Settings.from_env()


def news_item() -> NewsItem:
    return NewsItem(
        title="Dubai used car market gains a new buyer service",
        publisher="Example Automotive",
        url="https://news.example/dubai-cars",
        published_at=datetime(2026, 7, 28, 8, tzinfo=UTC),
        summary="The service is available to UAE vehicle buyers.",
    )


def news_evidence() -> NewsEvidence:
    now = datetime(2026, 7, 28, 10, tzinfo=UTC)
    return NewsEvidence.model_validate(
        {
            "evidence_id": "evidence-1",
            "semantic_fingerprint": "semantic-1",
            "feed_id": "example_news",
            "feed_revision_id": "feed-revision-1",
            "publisher_name": "Example Automotive",
            "publisher_domains": ["news.example"],
            "source_url": "https://news.example/dubai-cars",
            "canonical_url": "https://news.example/dubai-cars",
            "title": "Dubai used car market gains a new buyer service",
            "summary": "The service is available to UAE vehicle buyers.",
            "published_at": datetime(2026, 7, 28, 8, tzinfo=UTC),
            "image_source_url": "https://news.example/image.jpg",
            "image_final_url": "https://news.example/image.jpg",
            "image_storage_uri": "file:///tmp/news.jpg",
            "image_sha256": "a" * 64,
            "image_content_type": "image/jpeg",
            "image_size_bytes": 10_000,
            "image_source_type": "page_metadata",
            "source_item_sha256": "b" * 64,
            "evidence_created_at": now,
            "fetched_at": now,
            "last_checked_at": now,
            "valid_until": datetime(2026, 8, 28, 10, tzinfo=UTC),
            "freshness_status": FreshnessStatus.ACTIVE,
        }
    )


def test_atom_feed_is_parsed_with_publisher_hint() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Dubai automotive market launches buyer service</title>
      <link href="https://news.example/atom-item" />
      <updated>2026-07-28T08:00:00Z</updated>
      <summary>New UAE car buyers can use the service.</summary></entry>
    </feed>"""

    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 28, 10, tzinfo=UTC),
        max_age_days=7,
        limit=3,
        publisher_hint="Example Publisher",
    )

    assert len(items) == 1
    assert items[0].publisher == "Example Publisher"
    assert items[0].url == "https://news.example/atom-item"


def test_aggregator_article_url_is_rejected() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
      <title>Dubai automotive market launches buyer service</title>
      <link>https://news.google.com/articles/example</link>
      <pubDate>Tue, 28 Jul 2026 08:00:00 +0000</pubDate>
      <source>Example Publisher</source>
      <description>New UAE car buyers can use the service.</description>
    </item></channel></rss>"""

    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 28, 10, tzinfo=UTC),
        max_age_days=7,
        limit=3,
    )

    assert items == []


def test_person_name_containing_car_is_not_automotive_news() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel><item>
      <title>UAE Team Emirates best moments for Tadej Pogacar</title>
      <link>https://publisher.example/sport/cycling/pogacar</link>
      <pubDate>Wed, 29 Jul 2026 04:29:09 +0000</pubDate>
      <source>The National</source>
      <description>Tour de France cycling highlights from the UAE-backed team.</description>
    </item></channel></rss>"""

    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 29, 7, tzinfo=UTC),
        max_age_days=7,
        limit=3,
    )

    assert items == []


def test_news_feed_registry_can_be_managed(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "news-registry.db")
    feed = NewsFeedConfiguration.model_validate(
        {
            "name": "example_news",
            "publisher": "Example News",
            "url": "https://news.example/feed.xml",
            "sample_count": 3,
        }
    )

    repository.save_news_feed_configuration(feed)
    stored = repository.list_news_feed_configurations()
    removed = repository.delete_news_feed_configuration(feed.name)

    assert stored == [feed]
    assert removed is True
    assert repository.list_news_feed_configurations() == []


@pytest.mark.asyncio
async def test_news_digest_is_idempotent_and_pending_is_requeued(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import pro_news

    repository = LocalRepository(tmp_path / "pro-news.db")
    settings = pro_news_settings(monkeypatch)
    evidence = news_evidence()
    repository.save_news_evidence(evidence)

    async def fake_ingest(*_args: object, **_kwargs: object) -> list[NewsEvidence]:
        return [evidence]

    monkeypatch.setattr(pro_news.NewsIngestionService, "ingest", fake_ingest)
    dispatcher = FakeContentDispatcher()

    first = await reconcile_pro_news_publication(repository, settings, dispatcher)
    second = await reconcile_pro_news_publication(repository, settings, dispatcher)
    record = repository.list_outbox(limit=1)[0]
    repository.update_outbox(record.delivery_id, OutboxState.SENT, telegram_message_id="42")
    third, _items = await preview_pro_news_publication(repository, settings)

    assert first.created == 1 and first.selected == 1
    assert second.requeued == 1 and second.selected == 1
    assert third.unpublished == 0 and third.sent == 1
    assert len(dispatcher.payloads) == 2
    assert record.template_version == PRO_NEWS_TEMPLATE_VERSION
    assert dispatcher.payloads[0]["news_fingerprints"] == [evidence.semantic_fingerprint]


def test_digest_is_english_and_contains_only_sourced_links() -> None:
    rendered = format_pro_news_digest([news_item()])

    assert "Dubai & UAE Automotive Brief" in rendered
    assert "Example Automotive" in rendered
    assert "https://news.example/dubai-cars" in rendered
    assert "investment recommendation" not in rendered.casefold()


def test_admin_assets_expose_r73_controls() -> None:
    html = Path("web/admin.html").read_text(encoding="utf-8")
    javascript = Path("web/admin.js").read_text(encoding="utf-8")
    gateway = Path("infra/api-gateway.yaml").read_text(encoding="utf-8")

    assert 'id="pro-news-enabled"' in html
    assert 'id="news-feed-url"' in html
    assert "/admin/news-feeds" in javascript
    assert "/admin/news-feeds/{name}" in gateway


@pytest.mark.asyncio
async def test_admin_validates_and_manages_news_feed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "news-admin.db")
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(
            subject="owner", email="owner@example.com", admin=require_admin
        ),
    )

    async def fake_ingest(*_args: object, **_kwargs: object) -> list[NewsEvidence]:
        return [news_evidence()]

    monkeypatch.setattr(web.NewsIngestionService, "ingest", fake_ingest)
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        added = await client.post(
            "/admin/news-feeds",
            json={
                "name": "example_news",
                "publisher": "Example News",
                "url": "https://news.example/feed.xml",
            },
        )
        listed = await client.get("/admin/news-feeds")
        paused = await client.post(
            "/admin/news-feeds/example_news", json={"enabled": False}
        )
        removed = await client.post("/admin/news-feeds/example_news/remove")

    assert added.status_code == 200
    assert listed.json()["items"][0]["sample_count"] == 1
    assert paused.json()["feed"]["enabled"] is False
    assert removed.json() == {"ok": True, "name": "example_news"}

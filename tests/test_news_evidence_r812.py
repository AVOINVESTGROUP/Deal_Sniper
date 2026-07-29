"""Контракт единого иллюстрированного news evidence R8.1.2."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from src.config import Settings
from src.domain.models import NewsFeedConfiguration, OutboxRecord, OutboxState
from src.news import NewsItem, parse_news_feed
from src.news_evidence import NewsIngestionService, load_news_asset
from src.storage import LocalRepository


def test_rss_media_image_is_extracted_and_configured_publisher_wins() -> None:
    payload = b"""<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item>
    <title>Dubai automotive market adds a used car service</title>
    <link>https://publisher.example/dubai-car-service</link>
    <pubDate>Wed, 29 Jul 2026 08:00:00 +0000</pubDate>
    <source>Wrong Aggregator</source>
    <description>UAE car buyers receive a new service.</description>
    <media:content url="https://cdn.publisher.example/story.webp" type="image/webp" />
    </item></channel></rss>"""

    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 29, 10, tzinfo=UTC),
        max_age_days=7,
        limit=3,
        publisher_hint="Verified Publisher",
    )

    assert items[0].publisher == "Verified Publisher"
    assert items[0].image_url == "https://cdn.publisher.example/story.webp"
    assert items[0].image_source_type == "rss_media"


@pytest.mark.asyncio
async def test_ingestion_persists_immutable_asset_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import news_evidence

    repository = LocalRepository(tmp_path / "news.db")
    settings = Settings.from_env()
    settings = replace(settings, local_raw_snapshots_path=tmp_path / "raw")
    item = NewsItem(
        title="Dubai used car market receives a new vehicle service",
        publisher="Example Automotive",
        url="https://news.example/story",
        published_at=datetime(2026, 7, 29, 8, tzinfo=UTC),
        summary="The UAE automotive service is available to car buyers.",
    )

    async def fake_latest(*_args: object, **_kwargs: object) -> list[NewsItem]:
        return [item]

    monkeypatch.setattr(news_evidence.DubaiAutoNewsClient, "latest", fake_latest)
    image = b"\xff\xd8\xff" + (b"x" * 5_000)

    class FakeResponse:
        def __init__(self, url: str, *, text: str = "", content: bytes = b"") -> None:
            self.url = url
            self.status_code = 200
            self.text = text
            self.content = content
            self.headers = {"content-type": "image/jpeg"} if content else {}

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            if url == item.url:
                return FakeResponse(
                    url,
                    text='<meta property="og:image" content="https://cdn.news.example/story.jpg">',
                )
            return FakeResponse(url, content=image)

    monkeypatch.setattr(news_evidence.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    feed = NewsFeedConfiguration(
        name="example_news",
        publisher="Example Automotive",
        url="https://news.example/feed.xml",
        publisher_domains=["news.example"],
        image_domains=["cdn.news.example"],
    )
    second_feed = feed.model_copy(update={"name": "second_news"})
    service = NewsIngestionService(repository, settings)
    first = await service.ingest(
        [feed, second_feed], now=datetime(2026, 7, 29, 10, tzinfo=UTC)
    )
    second = await service.ingest([feed], now=datetime(2026, 7, 29, 11, tzinfo=UTC))

    assert first[0].evidence_id == second[0].evidence_id
    assert first[0].evidence_created_at == second[0].evidence_created_at
    assert first[0].image_sha256 == second[0].image_sha256
    assert await load_news_asset(settings, first[0].image_storage_uri) == image
    assert repository.active_news_evidence()[0].publisher_name == "Example Automotive"
    health = repository.source_health()
    assert health["news:example_news"]["accepted"] == 1
    assert health["news:second_news"]["accepted"] == 1

    async def transient_failure(*_args: object, **_kwargs: object) -> list[NewsItem]:
        raise httpx.ReadTimeout("temporary feed failure")

    monkeypatch.setattr(
        news_evidence.DubaiAutoNewsClient, "latest", transient_failure
    )
    assert await service.ingest([feed], now=datetime(2026, 7, 29, 12, tzinfo=UTC)) == []
    assert repository.active_news_evidence()[0].evidence_id == first[0].evidence_id
    assert "ReadTimeout" in repository.source_health()["news:example_news"]["error"]


@pytest.mark.asyncio
async def test_unapproved_image_redirect_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import news_evidence

    repository = LocalRepository(tmp_path / "news-reject.db")
    settings = Settings.from_env()
    item = NewsItem(
        title="Dubai automotive market receives a used car service",
        publisher="Example Automotive",
        url="https://news.example/story",
        published_at=datetime(2026, 7, 29, 8, tzinfo=UTC),
        summary="The UAE vehicle service is available to car buyers.",
        image_url="https://cdn.news.example/story.jpg",
        image_source_type="rss_media",
    )

    async def fake_latest(*_args: object, **_kwargs: object) -> list[NewsItem]:
        return [item]

    monkeypatch.setattr(news_evidence.DubaiAutoNewsClient, "latest", fake_latest)

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str) -> SimpleNamespace:
            if url == item.url:
                return SimpleNamespace(url=url, text="", raise_for_status=lambda: None)
            return SimpleNamespace(
                url="https://untrusted.example/image.jpg",
                headers={"content-type": "image/jpeg"},
                content=b"\xff\xd8\xff" + (b"x" * 5_000),
                status_code=200,
                raise_for_status=lambda: None,
            )

    monkeypatch.setattr(news_evidence.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    feed = NewsFeedConfiguration(
        name="example_news",
        publisher="Example Automotive",
        url="https://news.example/feed.xml",
        publisher_domains=["news.example"],
        image_domains=["cdn.news.example"],
    )

    assert await NewsIngestionService(repository, settings).ingest([feed]) == []
    assert repository.active_news_evidence() == []


@pytest.mark.asyncio
async def test_news_delivery_uses_saved_asset_and_never_falls_back_to_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "delivery.db")
    settings = replace(
        Settings.from_env(),
        delivery_enabled=True,
        telegram_bot_token="test-token",
        internal_task_secret="",
    )
    image = b"\xff\xd8\xff" + (b"x" * 5_000)
    import hashlib

    checksum = hashlib.sha256(image).hexdigest()
    payload: dict[str, object] = {
        "delivery_id": "news-delivery-1",
        "publication_event_id": "news-event-1",
        "target_id": "-1001",
        "text": "<b>Sourced news</b>",
        "template_version": "free-news/v1",
        "news_evidence_id": "evidence-1",
        "image_storage_uri": "file:///immutable/news.jpg",
        "image_sha256": checksum,
        "image_content_type": "image/jpeg",
        "article_button_label": "Read article",
        "article_button_url": "https://news.example/story",
    }
    repository.put_outbox(
        OutboxRecord(
            delivery_id="news-delivery-1",
            decision_id="evidence-1",
            recipient="-1001",
            template_version="free-news/v1",
            format="telegram-photo",
            payload=payload,
        )
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeBot:
        def __init__(self, _token: str) -> None:
            pass

        async def __aenter__(self) -> FakeBot:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def send_photo(self, **kwargs: Any) -> SimpleNamespace:
            calls.append(("photo", kwargs))
            return SimpleNamespace(message_id=91)

        async def send_message(self, **kwargs: Any) -> SimpleNamespace:
            calls.append(("text", kwargs))
            return SimpleNamespace(message_id=92)

    async def fake_load(*_args: object) -> bytes:
        return image

    monkeypatch.setattr(web, "settings", settings)
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(web, "Bot", FakeBot)
    monkeypatch.setattr(web, "load_news_asset", fake_load)

    result = await web.deliver_content_task(
        web.ContentDeliveryTask.model_validate(payload),
        x_cloudtasks_taskname="news-delivery-task",
    )

    stored = repository.get_outbox("news-delivery-1")
    assert result == {"ok": True}
    assert [kind for kind, _ in calls] == ["photo"]
    assert stored is not None and stored.state is OutboxState.SENT
    assert stored.telegram_message_id == "91"

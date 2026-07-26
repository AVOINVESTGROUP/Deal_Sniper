"""Проверки естественного диалога и fail-closed новостной ленты."""

from datetime import UTC, datetime

from src.chat import ChatIntent, classify_chat_intent, effective_chat_id
from src.news import format_news, parse_news_feed


def test_chat_intents_are_selected_before_car_search() -> None:
    assert classify_chat_intent("Hello") is ChatIntent.GREETING
    assert classify_chat_intent("Latest Dubai auto news") is ChatIntent.NEWS
    assert classify_chat_intent("Show market overview") is ChatIntent.MARKET
    assert classify_chat_intent("Find a car") is ChatIntent.FIND_CAR
    assert classify_chat_intent("Upgrade to Pro") is ChatIntent.UPGRADE


def test_migrated_supergroup_id_takes_priority() -> None:
    message = {"chat": {"id": -123}, "migrate_to_chat_id": -1004451580668}
    assert effective_chat_id(message) == -1004451580668


def test_news_requires_provenance_and_freshness() -> None:
    payload = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item>
        <title>Fresh Dubai automotive headline</title>
        <link>https://news.example/fresh</link>
        <pubDate>Sat, 25 Jul 2026 08:00:00 GMT</pubDate>
        <source url="https://publisher.example">Example News</source>
      </item>
      <item>
        <title>Old headline</title>
        <link>https://news.example/old</link>
        <pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate>
        <source url="https://publisher.example">Example News</source>
      </item>
      <item>
        <title>Missing publisher</title>
        <link>https://news.example/missing</link>
        <pubDate>Sat, 25 Jul 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 26, tzinfo=UTC),
        max_age_days=14,
        limit=3,
    )

    assert len(items) == 1
    assert items[0].publisher == "Example News"
    rendered = format_news(items)
    assert "25 Jul 2026" in rendered
    assert "https://news.example/fresh" in rendered
    assert "Example News" in rendered


def test_news_rejects_non_https_and_duplicates() -> None:
    payload = b"""<rss><channel>
      <item><title>Same Dubai car update</title><link>https://example.com/1</link>
        <pubDate>Sat, 25 Jul 2026 08:00:00 GMT</pubDate><source>Publisher</source></item>
      <item><title>Same Dubai car update</title><link>https://example.com/2</link>
        <pubDate>Sat, 25 Jul 2026 09:00:00 GMT</pubDate><source>Publisher</source></item>
      <item><title>Unsafe UAE car update</title><link>http://example.com/3</link>
        <pubDate>Sat, 25 Jul 2026 10:00:00 GMT</pubDate><source>Publisher</source></item>
    </channel></rss>"""
    items = parse_news_feed(
        payload,
        now=datetime(2026, 7, 26, tzinfo=UTC),
        max_age_days=14,
        limit=3,
    )
    assert len(items) == 1

"""Контракты атомарной парной доставки новостей R8.1.2.1."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from src.config import Settings
from src.domain.models import OutboxState
from src.pro_news import (
    FREE_NEWS_TEMPLATE_VERSION,
    NEWS_PAIR_BLOCKED_EVENT,
    NEWS_PAIR_READY_EVENT,
    PRO_NEWS_TEMPLATE_VERSION,
    _commit_news_card,
    news_pair_delivery_gate,
    reconcile_pro_news_publication,
)
from src.storage import LocalRepository
from tests.test_pro_news_r73 import news_evidence


class RecordingDispatcher:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.fail_on = fail_on

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)
        if self.fail_on == len(self.payloads):
            raise RuntimeError("controlled enqueue failure")


def pair_settings() -> Settings:
    return replace(
        Settings.from_env(),
        delivery_enabled=True,
        pro_news_enabled=True,
        telegram_channel_id="-100-free",
        telegram_pro_channel_id="-100-pro",
    )


def committed_pair(repository: LocalRepository) -> tuple[str, str, str]:
    evidence = news_evidence()
    pro, _ = _commit_news_card(
        repository,
        evidence,
        "-100-pro",
        PRO_NEWS_TEMPLATE_VERSION,
        "",
    )
    free, _ = _commit_news_card(
        repository,
        evidence,
        "-100-free",
        FREE_NEWS_TEMPLATE_VERSION,
        "",
    )
    return evidence.evidence_id, pro.delivery_id, free.delivery_id


@pytest.mark.asyncio
async def test_pending_pair_enqueues_both_once_and_pro_is_first(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "pair.db")
    evidence_id, pro_id, free_id = committed_pair(repository)
    dispatcher = RecordingDispatcher()

    first = await reconcile_pro_news_publication(repository, pair_settings(), dispatcher)
    second = await reconcile_pro_news_publication(repository, pair_settings(), dispatcher)

    assert [item["template_version"] for item in dispatcher.payloads] == [
        PRO_NEWS_TEMPLATE_VERSION,
        FREE_NEWS_TEMPLATE_VERSION,
    ]
    assert {item["delivery_id"] for item in dispatcher.payloads} == {pro_id, free_id}
    assert first.paired_enqueued == 1 and first.requeued == 2
    assert second.paired_enqueued == 1 and second.requeued == 0
    assert any(
        event["event_type"] == NEWS_PAIR_READY_EVENT
        and event["payload"]["news_evidence_id"] == evidence_id
        for event in repository.list_audit_events(20)
    )


@pytest.mark.asyncio
async def test_missing_pair_side_is_blocked_without_task(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "missing.db")
    evidence = news_evidence()
    _commit_news_card(
        repository,
        evidence,
        "-100-pro",
        PRO_NEWS_TEMPLATE_VERSION,
        "",
    )
    dispatcher = RecordingDispatcher()

    result = await reconcile_pro_news_publication(repository, pair_settings(), dispatcher)

    assert dispatcher.payloads == []
    assert result.blocked_pair == 1 and result.failures == 1
    assert any(
        event["event_type"] == NEWS_PAIR_BLOCKED_EVENT
        for event in repository.list_audit_events(10)
    )


@pytest.mark.asyncio
async def test_mismatching_image_blocks_entire_pair(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "mismatch.db")
    evidence_id, _pro_id, free_id = committed_pair(repository)
    free = repository.get_outbox(free_id)
    assert free is not None
    # LocalRepository сохраняет outbox идемпотентно, поэтому создаём Free сразу
    # из той же evidence revision с намеренно несовпадающим immutable image SHA.
    repository = LocalRepository(tmp_path / "mismatch-rebuilt.db")
    evidence = news_evidence()
    _commit_news_card(
        repository,
        evidence,
        "-100-pro",
        PRO_NEWS_TEMPLATE_VERSION,
        "",
    )
    mismatched = evidence.model_copy(update={"image_sha256": "f" * 64})
    _commit_news_card(
        repository,
        mismatched,
        "-100-free",
        FREE_NEWS_TEMPLATE_VERSION,
        "",
    )
    dispatcher = RecordingDispatcher()

    result = await reconcile_pro_news_publication(repository, pair_settings(), dispatcher)

    assert dispatcher.payloads == []
    assert result.blocked_pair == 1
    event = next(
        item
        for item in repository.list_audit_events(10)
        if item["event_type"] == NEWS_PAIR_BLOCKED_EVENT
    )
    assert event["event_type"] == NEWS_PAIR_BLOCKED_EVENT
    assert event["payload"]["news_evidence_id"] == evidence_id
    assert event["payload"]["reason"] == "pair_image_sha256_mismatch"


@pytest.mark.asyncio
async def test_second_enqueue_failure_never_opens_delivery_gate(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "failure.db")
    evidence_id, pro_id, free_id = committed_pair(repository)
    dispatcher = RecordingDispatcher(fail_on=2)

    result = await reconcile_pro_news_publication(repository, pair_settings(), dispatcher)
    pro_gate = news_pair_delivery_gate(repository, pair_settings(), pro_id, evidence_id)
    free_gate = news_pair_delivery_gate(repository, pair_settings(), free_id, evidence_id)

    assert len(dispatcher.payloads) == 2
    assert result.blocked_pair == 1 and result.failures == 1
    assert pro_gate == (False, False, "pair_not_enqueued")
    assert free_gate == (False, False, "pair_not_enqueued")
    assert not any(
        event["event_type"] == NEWS_PAIR_READY_EVENT
        for event in repository.list_audit_events(20)
    )


@pytest.mark.asyncio
async def test_free_delivery_waits_for_exact_sent_pro(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "gate.db")
    evidence_id, pro_id, free_id = committed_pair(repository)
    await reconcile_pro_news_publication(repository, pair_settings(), RecordingDispatcher())

    assert news_pair_delivery_gate(repository, pair_settings(), pro_id, evidence_id) == (
        True,
        False,
        "ready",
    )
    assert news_pair_delivery_gate(repository, pair_settings(), free_id, evidence_id) == (
        False,
        False,
        "pro_not_sent",
    )
    repository.update_outbox(
        pro_id,
        OutboxState.SENT,
        telegram_message_id="101",
    )
    assert news_pair_delivery_gate(repository, pair_settings(), free_id, evidence_id) == (
        True,
        False,
        "ready",
    )


@pytest.mark.asyncio
async def test_news_only_entrypoint_does_not_invoke_other_publishers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src import content_job

    repository = LocalRepository(tmp_path / "news-only.db")
    settings = pair_settings()
    calls: list[str] = []

    monkeypatch.setattr(
        content_job.DealService,
        "from_settings",
        lambda _settings: SimpleNamespace(repository=repository),
    )
    monkeypatch.setattr(content_job, "effective_settings", lambda _repo, value: value)
    monkeypatch.setattr(content_job, "CloudTaskDispatcher", lambda _settings: RecordingDispatcher())

    async def fake_news(*_args: object, **_kwargs: object) -> Any:
        calls.append("news")
        from src.pro_news import ProNewsPublicationSummary

        return ProNewsPublicationSummary(enabled=True)

    monkeypatch.setattr(content_job, "reconcile_pro_news_publication", fake_news)
    monkeypatch.setattr(
        content_job,
        "reconcile_pro_publications",
        lambda *_args, **_kwargs: pytest.fail("deal publisher was invoked"),
    )
    monkeypatch.setattr(
        content_job,
        "reconcile_free_publications",
        lambda *_args, **_kwargs: pytest.fail("free deal reconciliation was invoked"),
    )
    monkeypatch.setattr(
        content_job,
        "enqueue_market_pulse",
        lambda *_args, **_kwargs: pytest.fail("Market Pulse was invoked"),
    )

    await content_job.run_news_publication(settings)

    assert calls == ["news"]

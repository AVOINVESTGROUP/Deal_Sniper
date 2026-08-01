"""Проверки деградации read-only статуса облачных компонентов."""

import pytest

from src.admin_cloud import _get_items, scheduler_action
from src.firestore_storage import _aggregation_count


class FakeResponse:
    ok = False
    status_code = 403


class FakeSession:
    def get(self, url: str, timeout: int) -> FakeResponse:
        return FakeResponse()


def test_unavailable_cloud_component_does_not_break_admin_panel() -> None:
    result = _get_items(FakeSession(), "https://example.invalid", "jobs", ("name", "state"))  # type: ignore[arg-type]
    assert result == [{"state": "UNAVAILABLE", "http_status": 403}]


class FakeAggregation:
    value = 17


class FakeCountQuery:
    def get(self) -> list[list[FakeAggregation]]:
        return [[FakeAggregation()]]


class FakeQuery:
    def count(self, alias: str) -> FakeCountQuery:
        assert alias == "total"
        return FakeCountQuery()


def test_firestore_aggregation_count_does_not_stream_documents() -> None:
    assert _aggregation_count(FakeQuery()) == 17


def test_scheduler_action_rejects_resources_outside_allowlist_before_cloud_call() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        scheduler_action("project", "region", "unrelated-production-job", "pause")
    with pytest.raises(ValueError, match="run, pause и resume"):
        scheduler_action("project", "region", "deal-sniper-collector", "delete")

"""Проверки деградации read-only статуса облачных компонентов."""

from src.admin_cloud import _get_items


class FakeResponse:
    ok = False
    status_code = 403


class FakeSession:
    def get(self, url: str, timeout: int) -> FakeResponse:
        return FakeResponse()


def test_unavailable_cloud_component_does_not_break_admin_panel() -> None:
    result = _get_items(FakeSession(), "https://example.invalid", "jobs", ("name", "state"))  # type: ignore[arg-type]
    assert result == [{"state": "UNAVAILABLE", "http_status": 403}]

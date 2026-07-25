from pathlib import Path

from src.web import TmaSettingsRequest, app


def test_tma_exposes_button_driven_user_routes() -> None:
    routes = {(route.path, method) for route in app.routes for method in route.methods or set()}
    assert ("/tma/settings", "GET") in routes
    assert ("/tma/settings", "POST") in routes
    assert ("/tma/searches", "GET") in routes
    assert ("/tma/searches", "POST") in routes
    assert ("/tma/searches/{search_id}", "POST") in routes
    assert ("/tma/summary", "GET") in routes
    assert ("/tma/market-watch", "GET") in routes


def test_tma_settings_request_cannot_override_owner() -> None:
    value = TmaSettingsRequest.model_validate(
        {"user_id": 999, "max_budget_aed": 120000, "makes": ["Toyota"]}
    )
    assert "user_id" not in value.model_dump()
    assert value.makes == ["Toyota"]


def test_tma_contains_primary_navigation_without_slash_commands() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "web" / "tma.js").read_text(encoding="utf-8")
    assert all(name in script for name in ("deals", "search", "saved", "settings", "admin"))
    assert "/source_on" not in script
    assert "/set_budget" not in script

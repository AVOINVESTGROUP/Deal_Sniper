"""Контракт пользовательского и административного Web-интерфейсов."""

import json
from pathlib import Path

import httpx
import pytest

from src.config import Settings
from src.web import app

WEB = Path(__file__).parents[1] / "web"
ROOT = WEB.parent


def test_user_app_contains_no_admin_interface() -> None:
    app = (WEB / "app.html").read_text(encoding="utf-8")
    script = (WEB / "tma.js").read_text(encoding="utf-8")

    assert 'id="admin-view"' not in app
    assert "renderAdmin" not in script
    assert '"admin"' not in script
    assert (WEB / "admin.html").exists()


def test_user_cards_render_listing_photos() -> None:
    script = (WEB / "tma.js").read_text(encoding="utf-8")
    styles = (WEB / "styles.css").read_text(encoding="utf-8")

    assert 'document.createElement("img")' in script
    assert "listing.image_urls?.[0]" in script
    assert ".deal-image" in styles


def test_user_app_contains_pro_subscription_offer() -> None:
    app = (WEB / "app.html").read_text(encoding="utf-8")
    script = (WEB / "tma.js").read_text(encoding="utf-8")

    assert "subscription-card" in app
    assert "/tma/subscription" in script
    assert "Subscribe to Pro" in script
    assert "price_aed" in script


def test_admin_is_a_separate_browser_console_with_email_password_auth() -> None:
    page = (WEB / "admin.html").read_text(encoding="utf-8")
    script = (WEB / "admin.js").read_text(encoding="utf-8")

    assert "telegram-web-app.js" not in page
    assert 'id="login-password"' in page
    assert "Cloud runtime" in page
    for section in (
        "Dashboard",
        "Sources",
        "Runs",
        "Listings",
        "Decisions",
        "Publications",
        "Users",
        "Revenue",
        "Errors",
        "Settings",
    ):
        assert section in page
    assert "signInWithEmailAndPassword" in script
    assert "runtime.adminApiBase" in script
    assert 'api + "/tma/auth"' not in script
    assert "/admin/sources/${button.dataset.source}/run" in script
    assert 'call("/admin/source-test"' in script
    assert 'call("/admin/sources"' in script
    assert "Promise.allSettled" in script
    assert "getIdToken(true)" in script
    assert "transientStatuses" in script
    assert "Add source" in page
    assert "Preview change" in page
    assert 'call("/admin/settings/preview"' in script
    assert 'call("/admin/settings/apply"' in script
    assert 'call("/admin/pro-publications"' in script
    assert 'call("/admin/pro-publications/run"' in script
    assert "Publication coverage" in page
    assert "/admin/schedulers/${encodeURIComponent(job)}/action" in script
    assert "Historical failed records are diagnostic only" in script
    assert "[hidden]{display:none!important}" in (WEB / "styles.css").read_text(encoding="utf-8")
    runtime = json.loads((WEB / "runtime-config.json").read_text(encoding="utf-8"))
    assert runtime["adminApiBase"] == runtime["apiBase"]


def test_hosting_csp_allows_required_firebase_and_gateway_connections() -> None:
    config = json.loads((WEB.parent / "firebase.json").read_text(encoding="utf-8"))
    headers = config["hosting"]["headers"]
    csp = next(
        header["value"]
        for rule in headers
        for header in rule["headers"]
        if header["key"] == "Content-Security-Policy"
    )

    assert "https://www.gstatic.com" in csp
    assert "https://deal-sniper-gateway-dglai0gq.ew.gateway.dev" in csp
    assert config["hosting"]["rewrites"] == []


def test_gateway_declares_preflight_for_every_admin_browser_route() -> None:
    gateway = (ROOT / "infra" / "api-gateway.yaml").read_text(encoding="utf-8")
    paths = (
        "/admin/overview",
        "/admin/settings",
        "/admin/settings/preview",
        "/admin/settings/apply",
        "/admin/settings/rollback",
        "/admin/runs",
        "/admin/schedulers/{job_name}/action",
        "/admin/listings",
        "/admin/decisions",
        "/admin/users",
        "/admin/errors",
        "/admin/sources",
        "/admin/source-test",
        "/admin/sources/{source_name}",
        "/admin/sources/{source_name}/run",
        "/admin/sources/{source_name}/remove",
        "/admin/outbox",
        "/admin/outbox/{delivery_id}/reconcile",
        "/admin/preview",
        "/content/market-pulse",
    )

    for path in paths:
        marker = f"  {path}:"
        assert marker in gateway
        block = gateway.split(marker, maxsplit=1)[1].split("\n  /", maxsplit=1)[0]
        assert "options:" in block, path


@pytest.mark.asyncio
async def test_admin_cors_preflight_and_error_response_keep_allowed_origin() -> None:
    origin = "https://avo-deal-sniper.web.app"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preflight = await client.options(
            "/admin/overview",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        unauthorized = await client.get("/admin/overview", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "Authorization" in preflight.headers["access-control-allow-headers"]
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == origin

    disallowed = "https://attacker.example"
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        rejected_origin = await client.options(
            "/admin/overview",
            headers={
                "Origin": disallowed,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert rejected_origin.status_code == 400
    assert "access-control-allow-origin" not in rejected_origin.headers


def test_cors_origins_are_explicit_https_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://avo-deal-sniper.web.app,https://preview.example.com/",
    )
    assert Settings.from_env().cors_allowed_origins == (
        "https://avo-deal-sniper.web.app",
        "https://preview.example.com",
    )

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://*.example.com")
    with pytest.raises(ValueError, match="точные HTTPS origins"):
        Settings.from_env()

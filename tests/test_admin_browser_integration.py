"""Опциональный authenticated browser smoke для Admin → Gateway → Cloud Run."""

import os
from pathlib import Path

import pytest

ADMIN_BROWSER_API_BASE = os.getenv("ADMIN_BROWSER_API_BASE", "").rstrip("/")
ADMIN_BROWSER_ID_TOKEN = os.getenv("ADMIN_BROWSER_ID_TOKEN", "")
ADMIN_BROWSER_ORIGIN = os.getenv(
    "ADMIN_BROWSER_ORIGIN", "https://avo-deal-sniper.web.app"
).rstrip("/")
CHROME_PATH = Path(
    os.getenv(
        "ADMIN_BROWSER_CHROME_PATH",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
)

pytestmark = pytest.mark.skipif(
    not ADMIN_BROWSER_API_BASE or not ADMIN_BROWSER_ID_TOKEN or not CHROME_PATH.exists(),
    reason="Требуются staging URL, краткоживущий Firebase token и Chrome",
)


def test_authenticated_admin_requests_work_in_real_chrome() -> None:
    """Chrome обязан выполнить все CORS-защищённые read-only Admin requests."""
    playwright_module = pytest.importorskip("playwright.sync_api")
    paths = [
        "/admin/overview",
        "/content/market-pulse",
        "/admin/preview",
        "/admin/outbox?state=unknown",
        "/admin/outbox?state=failed",
    ]
    with playwright_module.sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROME_PATH), headless=True)
        page = browser.new_page()

        def allow_staging_gateway(route: object) -> None:
            """Добавляет staging hostname только в CSP изолированного browser smoke."""
            response = route.fetch()  # type: ignore[attr-defined]
            headers = dict(response.headers)
            csp = headers.get("content-security-policy", "")
            if csp and ADMIN_BROWSER_API_BASE not in csp:
                headers["content-security-policy"] = csp.replace(
                    "connect-src ", f"connect-src {ADMIN_BROWSER_API_BASE} ", 1
                )
            route.fulfill(response=response, headers=headers)  # type: ignore[attr-defined]

        page.route(f"{ADMIN_BROWSER_ORIGIN}/admin.html*", allow_staging_gateway)
        page.goto(f"{ADMIN_BROWSER_ORIGIN}/admin.html", wait_until="domcontentloaded")
        result = page.evaluate(
            """
            async ({base, token, paths}) => Promise.all(paths.map(async (path) => {
              try {
                const response = await fetch(base + path, {
                  cache: "no-store",
                  headers: {Authorization: `Bearer ${token}`},
                });
                return {path, status: response.status, ok: response.ok};
              } catch (error) {
                return {path, status: 0, ok: false, error: String(error)};
              }
            }))
            """,
            {"base": ADMIN_BROWSER_API_BASE, "token": ADMIN_BROWSER_ID_TOKEN, "paths": paths},
        )
        browser.close()

    assert result == [{"path": path, "status": 200, "ok": True} for path in paths]

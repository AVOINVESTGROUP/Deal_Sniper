"""Контракт пользовательского и административного Web-интерфейсов."""

from pathlib import Path

WEB = Path(__file__).parents[1] / "web"


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


def test_admin_uses_telegram_auth_instead_of_disabled_google_provider() -> None:
    page = (WEB / "admin.html").read_text(encoding="utf-8")
    script = (WEB / "admin.js").read_text(encoding="utf-8")

    assert "telegram-web-app.js" in page
    assert "Open admin panel in Telegram" in page
    assert "signInWithCustomToken" in script
    assert 'api + "/tma/auth"' in script
    assert "signInWithPopup" not in script
    assert "GoogleAuthProvider" not in script

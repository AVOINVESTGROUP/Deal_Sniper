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

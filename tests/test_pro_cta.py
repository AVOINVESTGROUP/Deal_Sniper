"""Проверки ротации, безопасности и идемпотентности Free → Pro CTA."""

from pathlib import Path

from src.pro_cta import (
    append_pro_cta,
    pro_cta_count,
    pro_cta_for_index,
    validated_subscription_url,
)
from src.storage import LocalRepository
from src.web import publication_cta_keyboard


def test_approved_cta_pool_has_thirty_unique_variants() -> None:
    variants = [pro_cta_for_index(index) for index in range(pro_cta_count())]

    assert len(variants) >= 30
    assert len({item.variant_id for item in variants}) == len(variants)
    assert len({item.text for item in variants}) == len(variants)
    assert len({item.button_label for item in variants}) == len(variants)
    assert len({item.fingerprint for item in variants}) == len(variants)
    assert all(
        not any("\u0400" <= character <= "\u04ff" for character in item.text)
        for item in variants
    )


def test_repository_reserves_full_cycle_and_keeps_retry_stable(tmp_path: Path) -> None:
    repository = LocalRepository(tmp_path / "cta.db")
    count = pro_cta_count()

    assigned = [
        repository.reserve_pro_cta_variant(f"publication-{index}", count)
        for index in range(count)
    ]

    assert assigned == list(range(count))
    assert repository.reserve_pro_cta_variant("publication-7", count) == 7
    assert repository.reserve_pro_cta_variant("publication-next", count) == 0


def test_subscription_url_and_html_block_are_fail_closed() -> None:
    assert validated_subscription_url("https://t.me/+paid-channel")
    assert validated_subscription_url("https://telegram.me/$paid-channel")
    assert validated_subscription_url("http://t.me/+paid-channel") is None
    assert validated_subscription_url("https://example.com/pro") is None
    assert validated_subscription_url("https://t.me/") is None

    cta = pro_cta_for_index(0)
    rendered = append_pro_cta("<b>Car</b>", cta)
    assert rendered.startswith("<b>Car</b>")
    assert "<b>Go Pro</b>" in rendered
    assert cta.text in rendered


def test_publication_keyboard_contains_direct_subscription_button() -> None:
    keyboard = publication_cta_keyboard("Unlock full analysis", "https://t.me/+paid-channel")

    assert keyboard is not None
    assert keyboard.to_dict() == {
        "inline_keyboard": [
            [
                {
                    "text": "Unlock full analysis",
                    "url": "https://t.me/+paid-channel",
                }
            ]
        ]
    }
    assert publication_cta_keyboard("Upgrade", "https://example.com/pro") is None

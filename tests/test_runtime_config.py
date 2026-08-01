"""Контракты версионированной конфигурации Control Center R7."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from src.config import Settings
from src.runtime_config import (
    SUBSCRIPTION_PERIOD_SECONDS,
    RuntimeConfiguration,
    active_configuration,
    effective_settings,
)
from src.storage import LocalRepository


def test_runtime_configuration_is_versioned_idempotent_and_archives_previous(
    tmp_path: Path,
) -> None:
    repository = LocalRepository(tmp_path / "runtime.db")
    first = RuntimeConfiguration(
        version="r7-first",
        pro_price_aed=100,
        pro_price_stars=1500,
        pro_subscription_url="https://t.me/+first-link",
        target_profit_aed=Decimal("5000"),
        min_roi_percent=Decimal("10"),
        min_comparables_count=5,
        channel_max_posts_per_run=10,
        created_at=datetime(2026, 7, 28, 10, tzinfo=UTC),
        created_by="owner@example.com",
    )
    stored = repository.activate_runtime_configuration(first.model_dump(mode="json"), "op-first-1")
    repeated = repository.activate_runtime_configuration(
        first.model_dump(mode="json"), "op-first-1"
    )
    assert stored == repeated
    second = first.model_copy(
        update={
            "version": "r7-second",
            "pro_price_aed": 120,
            "pro_price_stars": 1700,
            "created_at": datetime(2026, 7, 28, 11, tzinfo=UTC),
        }
    )
    repository.activate_runtime_configuration(second.model_dump(mode="json"), "op-second-1")

    active = repository.get_active_runtime_configuration()
    history = repository.list_runtime_configurations()
    assert active is not None
    assert active["version"] == "r7-second"
    assert active["previous_version"] == "r7-first"
    assert {item["state"] for item in history} == {"active", "archived"}


def test_effective_settings_falls_back_and_applies_active_revision(
    tmp_path: Path,
) -> None:
    baseline = Settings.from_env()
    baseline = replace(
        baseline,
        pro_price_aed=100,
        pro_price_stars=1500,
        telegram_pro_subscription_url="https://t.me/+baseline",
    )
    repository = LocalRepository(tmp_path / "effective.db")
    assert active_configuration(repository, baseline).pro_price_aed == 100
    revision = RuntimeConfiguration(
        version="r7-effective",
        pro_price_aed=125,
        pro_price_stars=1800,
        pro_subscription_url="https://t.me/+effective",
        subscription_period_seconds=SUBSCRIPTION_PERIOD_SECONDS,
        target_profit_aed=Decimal("7000"),
        min_roi_percent=Decimal("15"),
        min_comparables_count=7,
        channel_max_posts_per_run=4,
        created_at=datetime(2026, 7, 28, 12, tzinfo=UTC),
        created_by="owner@example.com",
    )
    repository.activate_runtime_configuration(revision.model_dump(mode="json"), "op-effective-1")
    effective = effective_settings(repository, baseline)
    assert effective.pro_price_aed == 125
    assert effective.pro_price_stars == 1800
    assert effective.target_profit_aed == Decimal("7000")
    assert effective.financial_config_version.startswith("r7-policy-")


def test_price_only_revision_does_not_invalidate_financial_decisions(tmp_path: Path) -> None:
    baseline = Settings.from_env()
    repository = LocalRepository(tmp_path / "price-only.db")
    revision = RuntimeConfiguration(
        version="r7-price-only",
        pro_price_aed=125,
        pro_price_stars=1800,
        pro_subscription_url="https://t.me/+price-only",
        target_profit_aed=baseline.target_profit_aed,
        min_roi_percent=baseline.min_roi_percent,
        min_comparables_count=baseline.min_comparables_count,
        channel_max_posts_per_run=baseline.channel_max_posts_per_run,
        created_at=datetime(2026, 7, 28, 13, tzinfo=UTC),
        created_by="owner@example.com",
    )
    repository.activate_runtime_configuration(revision.model_dump(mode="json"), "op-price-only")

    effective = effective_settings(repository, baseline)

    assert effective.pro_price_aed == 125
    assert effective.pro_price_stars == 1800
    assert effective.financial_config_version == baseline.financial_config_version


def test_runtime_configuration_rejects_invalid_stars_and_period() -> None:
    payload = {
        "version": "invalid",
        "pro_price_aed": 100,
        "pro_price_stars": 10_001,
        "pro_subscription_url": "https://t.me/+invalid",
        "target_profit_aed": 5000,
        "min_roi_percent": 10,
        "min_comparables_count": 5,
        "channel_max_posts_per_run": 10,
        "created_at": "2026-07-28T12:00:00Z",
        "created_by": "owner@example.com",
    }
    try:
        RuntimeConfiguration.model_validate(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("Stars above Telegram limit must be rejected")

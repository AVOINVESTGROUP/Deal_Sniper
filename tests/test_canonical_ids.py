"""Golden fixtures канонических идентификаторов."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.ids import (
    canonical_hash,
    canonical_json,
    cloud_task_name,
    decision_id,
    delivery_id,
    migration_id,
    money_value,
    publication_revision_id,
    rate_value,
    verification_key,
)


def test_canonical_json_normalizes_unicode_decimal_sets_and_timestamp() -> None:
    value = {
        "name": "Cafe\u0301",
        "money": money_value(Decimal("12.5")),
        "rate": rate_value(Decimal("0.1")),
        "at": datetime(2026, 7, 25, 13, 0, 0, 123456, tzinfo=UTC),
        "tags": {"b", "a"},
        "nullable": None,
    }
    assert canonical_json(value) == (
        '{"at":"2026-07-25T13:00:00.123Z","money":"12.50",'
        '"name":"Café","nullable":null,"rate":"0.100000","tags":["a","b"]}'
    )


def test_null_and_missing_field_are_distinct() -> None:
    assert canonical_hash("fixture/v1", {"value": None}) != canonical_hash("fixture/v1", {})


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        canonical_json({"at": datetime(2026, 7, 25)})


def test_golden_ids_are_stable() -> None:
    verification = verification_key("dubicars", "dubicars:42", "abc", "dubicars/v3")
    decision = decision_id(
        listing_id="dubicars:42",
        content_hash="abc",
        engine_version="3.0.0",
        financial_config_version="provisional-2026-07-v1",
        verification_version="evidence-1",
        market_fingerprint_value="market-1",
    )
    delivery = delivery_id(
        decision_id_value=decision,
        recipient_id="telegram:user:7",
        template_version="pro/v1",
        format_name="telegram-html",
    )
    migration = migration_id("legacy/v1", "production/v2", datetime(2026, 7, 25, tzinfo=UTC))
    task = cloud_task_name("process", {"decision_id": decision})

    assert verification == "647e331cac9673607d98c18bdeebd7959b046a4352761c8e06f53132b8845d23"
    assert decision == "f02508852b3a995e0814919f0ccc9f64cc1a58caa0bdf910bbf14a95c0c1046c"
    assert delivery == "b00c8153b8d704104f90eea37daceaa993bbc2bf794c8efd296494e4ae629d24"
    assert migration == "38a06c84261d8862afab1c39403479ddd301417d1ed6cb99f856c34d324cdaae"
    assert task == ("process-420bb98780069f4f54db7ab7424aed711c4c27b3c19b0656c92369116160c8b3")


def test_publication_revision_identity_includes_recipient_and_template() -> None:
    revision = publication_revision_id(
        decision_id_value="decision-1",
        vehicle_id="vehicle-1",
        event_type="deal-candidate-free",
        recipient_id="-1001",
        template_version="free/v2",
    )

    assert revision == "e29880ac3261f091f7e5a09cd09fd9a5e6544cc870c055db2344b14dced2259f"
    assert revision != publication_revision_id(
        decision_id_value="decision-1",
        vehicle_id="vehicle-1",
        event_type="deal-candidate-free",
        recipient_id="-1002",
        template_version="free/v2",
    )
    assert revision != publication_revision_id(
        decision_id_value="decision-1",
        vehicle_id="vehicle-1",
        event_type="deal-candidate-free",
        recipient_id="-1001",
        template_version="free/v3",
    )

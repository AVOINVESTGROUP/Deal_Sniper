"""Канонические идентификаторы домена и инфраструктуры."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CanonicalDecimal:
    """Decimal с явно заданным числом знаков для ID-контракта."""

    value: Decimal
    places: int


def money_value(value: Decimal) -> CanonicalDecimal:
    """Возвращает денежное значение с двумя знаками."""
    return CanonicalDecimal(value, 2)


def rate_value(value: Decimal) -> CanonicalDecimal:
    """Возвращает ставку с шестью знаками."""
    return CanonicalDecimal(value, 6)


def _decimal_string(value: Decimal, places: int) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), f".{places}f")


def _normalize(value: Any) -> Any:
    if isinstance(value, CanonicalDecimal):
        return _decimal_string(value.value, value.places)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Timestamp для canonical JSON должен содержать timezone")
        utc = value.astimezone(UTC)
        return utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(normalized, key=lambda item: canonical_json(item))
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError(f"Неподдерживаемый тип canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Сериализует значение в UTF-8 JSON без пробелов и неоднозначностей."""
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(schema: str, payload: Mapping[str, Any]) -> str:
    """Возвращает lowercase SHA-256 объекта с обязательным schema tag."""
    if not schema or "/" not in schema:
        raise ValueError("Schema tag должен содержать имя и версию")
    document = {"schema": schema, **payload}
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def verification_key(
    source: str,
    listing_id: str,
    content_hash: str,
    extractor_version: str,
) -> str:
    return canonical_hash(
        "verification-key/v1",
        {
            "source": source,
            "listing_id": listing_id,
            "content_hash": content_hash,
            "extractor_version": extractor_version,
        },
    )


def evidence_revision_id(payload: Mapping[str, Any]) -> str:
    return canonical_hash("evidence-revision/v1", payload)


def market_fingerprint(comparables: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(comparables, key=lambda item: canonical_json(item))
    return canonical_hash("market-fingerprint/v1", {"comparables": ordered})


def decision_id(
    *,
    listing_id: str,
    content_hash: str,
    engine_version: str,
    financial_config_version: str,
    verification_version: str,
    market_fingerprint_value: str,
) -> str:
    return canonical_hash(
        "decision-id/v1",
        {
            "listing_id": listing_id,
            "content_hash": content_hash,
            "engine_version": engine_version,
            "financial_config_version": financial_config_version,
            "verification_version": verification_version,
            "market_fingerprint": market_fingerprint_value,
        },
    )


def delivery_id(
    *, decision_id_value: str, recipient_id: str, template_version: str, format_name: str
) -> str:
    return canonical_hash(
        "delivery-id/v1",
        {
            "decision_id": decision_id_value,
            "delivery_recipient_id": recipient_id,
            "template_version": template_version,
            "format": format_name,
        },
    )


def operation_id(operation_type: str, subject: Mapping[str, Any]) -> str:
    return canonical_hash(
        "operation-id/v1",
        {"operation_type": operation_type, "subject": subject},
    )


def migration_id(source_schema: str, target_schema: str, export_watermark: datetime) -> str:
    return canonical_hash(
        "migration-id/v1",
        {
            "source_schema": source_schema,
            "target_schema": target_schema,
            "export_watermark": export_watermark,
        },
    )


def publication_event_id(
    *, decision_id_value: str, vehicle_id: str, event_type: str
) -> str:
    return canonical_hash(
        "publication-event-id/v1",
        {
            "decision_id": decision_id_value,
            "vehicle_id": vehicle_id,
            "event_type": event_type,
        },
    )


def cloud_task_name(prefix: str, identity: Mapping[str, Any]) -> str:
    """Формирует допустимое имя Cloud Task с тем же canonical hash."""
    normalized_prefix = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in prefix.casefold()
    ).strip("-")
    if not normalized_prefix:
        raise ValueError("Префикс Cloud Task пуст")
    return f"{normalized_prefix}-{canonical_hash('cloud-task-name/v1', identity)}"

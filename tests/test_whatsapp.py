"""Fail-closed контракты официального WhatsApp Cloud API adapter."""

from datetime import UTC, datetime

import pytest

from src.domain.models import PublicationEvent
from src.whatsapp import (
    WhatsAppAdapter,
    WhatsAppConfig,
    build_whatsapp_outbox,
)


@pytest.mark.asyncio
async def test_adapter_is_disabled_without_meta_credentials() -> None:
    adapter = WhatsAppAdapter(WhatsAppConfig(False, "", ""))

    with pytest.raises(RuntimeError):
        await adapter.send_template("971500000000", "deal", "en_US", [], opted_in=True)


def test_outbox_requires_explicit_opt_in() -> None:
    event = PublicationEvent(
        publication_event_id="event-1",
        decision_id="decision-1",
        vehicle_id="vehicle-1",
        event_type="deal",
        created_at=datetime(2026, 7, 25, tzinfo=UTC),
    )

    with pytest.raises(PermissionError):
        build_whatsapp_outbox(event, "971500000000", "deal", "en_US", [], opted_in=False)

    record, payload = build_whatsapp_outbox(
        event, "971500000000", "deal", "en_US", [], opted_in=True
    )
    assert record.format == "whatsapp-template"
    assert payload["opted_in"] is True

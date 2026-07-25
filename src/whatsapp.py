"""Официальный WhatsApp Business Cloud API adapter через общий outbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from src.domain.ids import delivery_id
from src.domain.models import OutboxRecord, PublicationEvent


@dataclass(frozen=True, slots=True)
class WhatsAppConfig:
    enabled: bool
    access_token: str
    phone_number_id: str
    api_version: str = "v23.0"

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.access_token and self.phone_number_id)


class WhatsAppAdapter:
    """Отправляет только opt-in recipient; WhatsApp Web automation не используется."""

    def __init__(self, config: WhatsAppConfig) -> None:
        self.config = config

    async def send_template(
        self,
        recipient: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]],
        *,
        opted_in: bool,
    ) -> str:
        if not self.config.ready:
            raise RuntimeError("WhatsApp adapter выключен или не имеет Meta credentials")
        if not opted_in:
            raise PermissionError("WhatsApp recipient не подтвердил opt-in")
        url = (
            f"https://graph.facebook.com/{self.config.api_version}/"
            f"{self.config.phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        headers = {"Authorization": f"Bearer {self.config.access_token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        messages = data.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise RuntimeError("Meta API не вернул message ID")
        return str(messages[0]["id"])


def build_whatsapp_outbox(
    event: PublicationEvent,
    recipient: str,
    template_name: str,
    language_code: str,
    components: list[dict[str, Any]],
    *,
    opted_in: bool,
) -> tuple[OutboxRecord, dict[str, object]]:
    """Создаёт delivery payload только для явно подтверждённого opt-in."""
    if not opted_in:
        raise PermissionError("WhatsApp recipient не подтвердил opt-in")
    stable_delivery_id = delivery_id(
        decision_id_value=event.publication_event_id,
        recipient_id=recipient,
        template_version=template_name,
        format_name="whatsapp-template",
    )
    payload: dict[str, object] = {
        "delivery_id": stable_delivery_id,
        "publication_event_id": event.publication_event_id,
        "recipient": recipient,
        "template_name": template_name,
        "language_code": language_code,
        "components": components,
        "opted_in": True,
    }
    return (
        OutboxRecord(
            delivery_id=stable_delivery_id,
            decision_id=event.decision_id,
            recipient=recipient,
            template_version=template_name,
            format="whatsapp-template",
            payload=payload,
        ),
        payload,
    )

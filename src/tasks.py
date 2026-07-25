"""Идемпотентная постановка обработки и Telegram-доставки в Cloud Tasks."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from src.config import Settings
from src.domain.ids import cloud_task_name, delivery_id


class CloudTaskDispatcher:
    """Создаёт именованные задачи: повторная постановка не создаёт дубль."""

    def __init__(self, settings: Settings) -> None:
        if not settings.cloud_run_api_url or not settings.cloud_tasks_location:
            raise ValueError("Cloud Tasks требует CLOUD_RUN_API_URL и CLOUD_TASKS_LOCATION")
        self.settings = settings
        self.client = tasks_v2.CloudTasksClient()

    async def enqueue_processing(
        self,
        listing_id: str,
        content_hash: str,
        engine_version: str,
        recalculation_epoch: str | None = None,
    ) -> None:
        epoch = recalculation_epoch or datetime.now(UTC).strftime("%Y%m%d%H")
        await self._enqueue(
            self.settings.listing_processing_queue,
            "/tasks/process-listing",
            {
                "listing_id": listing_id,
                "content_hash": content_hash,
                "engine_version": engine_version,
                "recalculation_epoch": epoch,
            },
            cloud_task_name(
                "process",
                {
                    "engine_version": engine_version,
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "recalculation_epoch": epoch,
                },
            ),
        )

    async def enqueue_processing_batch(
        self,
        pending: list[tuple[str, str]],
        engine_version: str,
        concurrency: int = 20,
        recalculation_epoch: str | None = None,
    ) -> None:
        """Ставит большой backfill в очередь с ограниченной параллельностью."""
        semaphore = asyncio.Semaphore(concurrency)

        async def enqueue(item: tuple[str, str]) -> None:
            async with semaphore:
                await self.enqueue_processing(
                    item[0], item[1], engine_version, recalculation_epoch
                )

        await asyncio.gather(*(enqueue(item) for item in pending))

    async def enqueue_delivery(self, payload: dict[str, Any]) -> None:
        identity = str(payload.get("_task_identity") or delivery_id(
            decision_id_value=str(payload.get("decision_id") or payload["listing_id"]),
            recipient_id=str(payload["target_id"]),
            template_version=str(payload.get("template_version", "pro/v1")),
            format_name=str(payload.get("format", "telegram")),
        ))
        await self._enqueue(
            self.settings.telegram_delivery_queue,
            "/tasks/deliver-telegram",
            payload,
            identity,
        )

    async def enqueue_content_delivery(self, payload: dict[str, Any]) -> None:
        identity = str(payload.get("_task_identity") or delivery_id(
            decision_id_value=str(payload["publication_event_id"]),
            recipient_id=str(payload["target_id"]),
            template_version=str(payload.get("template_version", "content/v1")),
            format_name="telegram-content",
        ))
        await self._enqueue(
            self.settings.telegram_delivery_queue,
            "/tasks/deliver-content",
            payload,
            identity,
        )

    async def enqueue_whatsapp_delivery(self, payload: dict[str, Any]) -> None:
        identity = str(
            payload.get("_task_identity")
            or delivery_id(
                decision_id_value=str(payload["publication_event_id"]),
                recipient_id=str(payload["recipient"]),
                template_version=str(payload["template_name"]),
                format_name="whatsapp-template",
            )
        )
        await self._enqueue(
            self.settings.telegram_delivery_queue,
            "/tasks/deliver-whatsapp",
            payload,
            identity,
        )

    async def _enqueue(
        self,
        queue_name: str,
        path: str,
        payload: dict[str, Any],
        identity: str,
    ) -> None:
        parent = self.client.queue_path(
            self.settings.google_cloud_project,
            self.settings.cloud_tasks_location,
            queue_name,
        )
        task_name = f"{parent}/tasks/{identity[:63]}"
        headers = {"Content-Type": "application/json"}
        if self.settings.internal_task_secret:
            headers["X-Internal-Task-Secret"] = self.settings.internal_task_secret
        request: dict[str, Any] = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": f"{self.settings.cloud_run_api_url}{path}",
            "headers": headers,
            "body": json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        }
        if self.settings.task_invoker_service_account:
            request["oidc_token"] = {
                "service_account_email": self.settings.task_invoker_service_account,
                "audience": self.settings.cloud_run_api_url,
            }
        try:
            await asyncio.to_thread(
                self.client.create_task,
                request={"parent": parent, "task": {"name": task_name, "http_request": request}},
            )
        except AlreadyExists:
            return

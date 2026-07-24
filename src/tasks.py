"""Идемпотентная постановка обработки и Telegram-доставки в Cloud Tasks."""

import asyncio
import hashlib
import json
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from src.config import Settings


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
    ) -> None:
        await self._enqueue(
            self.settings.listing_processing_queue,
            "/tasks/process-listing",
            {
                "listing_id": listing_id,
                "content_hash": content_hash,
                "engine_version": engine_version,
            },
            f"process:{engine_version}:{listing_id}:{content_hash}",
        )

    async def enqueue_processing_batch(
        self,
        pending: list[tuple[str, str]],
        engine_version: str,
        concurrency: int = 20,
    ) -> None:
        """Ставит большой backfill в очередь с ограниченной параллельностью."""
        semaphore = asyncio.Semaphore(concurrency)

        async def enqueue(item: tuple[str, str]) -> None:
            async with semaphore:
                await self.enqueue_processing(item[0], item[1], engine_version)

        await asyncio.gather(*(enqueue(item) for item in pending))

    async def enqueue_delivery(self, payload: dict[str, Any]) -> None:
        identity = (
            f"deliver:{payload['target_id']}:{payload['listing_id']}:"
            f"{payload['content_hash']}"
        )
        await self._enqueue(
            self.settings.telegram_delivery_queue,
            "/tasks/deliver-telegram",
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
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        task_name = f"{parent}/tasks/{digest}"
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

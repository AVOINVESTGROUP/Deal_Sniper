"""Запуск отдельных Cloud Run collector Jobs из Telegram API."""

import asyncio
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

from src.config import Settings


class CloudJobLauncher:
    """Запускает collector job, не удерживая Telegram webhook."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def run_collectors(self, source_names: list[str]) -> None:
        await asyncio.gather(*(self.run_collector(name) for name in source_names))

    async def run_collector(self, source_name: str) -> None:
        await asyncio.to_thread(self._run_collector_sync, source_name)

    def _run_collector_sync(self, source_name: str) -> None:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
        job_name = f"{self.settings.collector_job_prefix}-{source_name}"
        url = (
            "https://run.googleapis.com/v2/projects/"
            f"{self.settings.google_cloud_project}/locations/"
            f"{self.settings.google_cloud_region}/jobs/{job_name}:run"
        )
        response = session.post(url, json={"validateOnly": False}, timeout=30)
        response.raise_for_status()
        operation: dict[str, Any] = response.json()
        if not operation.get("name"):
            raise RuntimeError(f"Cloud Run не подтвердил запуск {job_name}")

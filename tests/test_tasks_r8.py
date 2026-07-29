"""R8: fail-closed постановка delivery и изоляция окружений."""

from typing import Any

import pytest

from src.config import Settings
from src.tasks import CloudTaskDispatcher


class FakeTasksClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f"projects/{project}/locations/{location}/queues/{queue}"

    def create_task(self, request: dict[str, Any]) -> None:
        self.created.append(request)


def cloud_settings(monkeypatch: pytest.MonkeyPatch, *, delivery: bool) -> Settings:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("CLOUD_TASKS_LOCATION", "me-central1")
    monkeypatch.setenv("CLOUD_RUN_API_URL", "https://api.example.test")
    monkeypatch.setenv("DELIVERY_ENABLED", "true" if delivery else "false")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "local")
    return Settings.from_env()


@pytest.mark.asyncio
async def test_delivery_off_creates_no_cloud_task(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = cloud_settings(monkeypatch, delivery=False)
    dispatcher = CloudTaskDispatcher(settings)
    fake = FakeTasksClient()
    dispatcher.client = fake  # type: ignore[assignment]

    await dispatcher.enqueue_content_delivery(
        {
            "publication_event_id": "event-1",
            "target_id": "channel-1",
            "template_version": "pro-news/v1",
        }
    )
    await dispatcher.enqueue_delivery(
        {
            "listing_id": "listing-1",
            "target_id": "channel-1",
            "template_version": "pro/v1",
        }
    )

    assert fake.created == []


def test_cloud_tasks_client_is_initialized_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = cloud_settings(monkeypatch, delivery=False)

    dispatcher = CloudTaskDispatcher(settings)

    assert dispatcher.client is None


def test_staging_delivery_requires_isolated_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DELIVERY_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("FIRESTORE_DATABASE", "(default)")
    monkeypatch.setenv("TELEGRAM_DELIVERY_QUEUE", "telegram-delivery")
    monkeypatch.setenv("PUBLISHER_JOB_NAME", "deal-sniper-publisher")

    with pytest.raises(ValueError, match="Staging delivery"):
        Settings.from_env()


def test_production_rejects_staging_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DELIVERY_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("TELEGRAM_DELIVERY_QUEUE", "telegram-delivery-staging")

    with pytest.raises(ValueError, match="Production delivery"):
        Settings.from_env()


def test_staging_rejects_production_telegram_recipient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DELIVERY_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("FIRESTORE_DATABASE", "deal-sniper-stage")
    monkeypatch.setenv("TELEGRAM_DELIVERY_QUEUE", "telegram-delivery-staging")
    monkeypatch.setenv("PUBLISHER_JOB_NAME", "deal-sniper-publisher-staging")
    monkeypatch.setenv("TELEGRAM_PRO_CHANNEL_ID", "-100-production")
    monkeypatch.setenv("PRODUCTION_TELEGRAM_CHANNEL_IDS", "-100-production,-100-free")

    with pytest.raises(ValueError, match="production recipient"):
        Settings.from_env()

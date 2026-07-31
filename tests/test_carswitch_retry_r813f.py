"""Регрессии bounded semantic retry CarSwitch из R8.1.3F."""

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from pydantic import HttpUrl

from src.config import Settings
from src.domain.models import ListingSnapshot, RawSnapshotMetadata
from src.raw_storage import LocalRawSnapshotArchive
from src.service import DealService
from src.sources.carswitch import (
    SEMANTIC_EMPTY_RESPONSE,
    CarSwitchSource,
    parse_carswitch_page,
)
from src.sources.dubicars import SourceError
from src.storage import LocalRepository

VALID_HTML = """
<script type="application/ld+json">
{
  "@type": "ItemList",
  "itemListElement": [{
    "mainEntity": {
      "name": "2021 Toyota Camry SE",
      "url": "https://carswitch.com/dubai/used-car/toyota/camry/2021/900001",
      "image": ["https://example.com/camry.jpg"],
      "brand": {"name": "Toyota"},
      "model": "Camry",
      "vehicleModelDate": "2021",
      "mileageFromOdometer": {"value": 41000},
      "offers": {"price": "79000", "priceCurrency": "AED"}
    }
  }]
}
</script>
"""


class RecordingArchive:
    """Запоминает каждую семантически проверяемую HTTP-попытку."""

    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.attempt_numbers: list[int | None] = []

    async def save(
        self,
        source: str,
        source_url: str,
        content_type: str,
        payload: bytes,
        *,
        attempt_number: int | None = None,
    ) -> RawSnapshotMetadata:
        self.payloads.append(payload)
        self.attempt_numbers.append(attempt_number)
        return RawSnapshotMetadata(
            source=source,
            source_url=HttpUrl(source_url),
            storage_uri=f"memory://{len(self.payloads)}",
            checksum_sha256="a" * 64,
            content_type=content_type,
            size_bytes=len(payload),
        )


INVALID_RESPONSES = [
    pytest.param(b"", "text/html", id="empty-body"),
    pytest.param(b"{}", "application/json", id="wrong-mime"),
    pytest.param(b"<html>maintenance</html>", "text/html", id="missing-item-list"),
]


@pytest.mark.parametrize(("invalid_body", "invalid_content_type"), INVALID_RESPONSES)
@pytest.mark.asyncio
async def test_empty_http_200_then_valid_item_list_recovers_within_budget(
    monkeypatch: pytest.MonkeyPatch,
    invalid_body: bytes,
    invalid_content_type: str,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        body = invalid_body if attempts == 1 else VALID_HTML.encode()
        content_type = invalid_content_type if attempts == 1 else "text/html; charset=utf-8"
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": content_type},
            request=request,
        )

    monkeypatch.setattr("src.sources.carswitch.asyncio.sleep", record_sleep)
    archive = RecordingArchive()
    source = CarSwitchSource("https://carswitch.test?page={page}", archive=archive)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        listings = await source._get_page_with_retry(client, "https://carswitch.test?page=1")

    assert attempts == 2
    assert archive.payloads == [invalid_body, VALID_HTML.encode()]
    assert archive.attempt_numbers == [1, 2]
    assert sleeps == [1]
    assert len(listings) == 1
    assert listings[0].source_listing_id == "900001"


@pytest.mark.parametrize(("invalid_body", "invalid_content_type"), INVALID_RESPONSES)
@pytest.mark.asyncio
async def test_three_empty_http_200_responses_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    invalid_body: bytes,
    invalid_content_type: str,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            content=invalid_body,
            headers={"content-type": invalid_content_type},
            request=request,
        )

    monkeypatch.setattr("src.sources.carswitch.asyncio.sleep", record_sleep)
    archive = RecordingArchive()
    source = CarSwitchSource("https://carswitch.test?page={page}", archive=archive)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError) as caught:
            await source._get_page_with_retry(client, "https://carswitch.test?page=1")

    assert attempts == 3
    assert archive.payloads == [invalid_body, invalid_body, invalid_body]
    assert archive.attempt_numbers == [1, 2, 3]
    assert sleeps == [1, 2]
    assert caught.value.category == SEMANTIC_EMPTY_RESPONSE
    assert caught.value.attempts == 3


@pytest.mark.asyncio
async def test_valid_item_list_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            content=VALID_HTML.encode(),
            headers={"content-type": "application/xhtml+xml; charset=utf-8"},
            request=request,
        )

    monkeypatch.setattr("src.sources.carswitch.asyncio.sleep", record_sleep)
    archive = RecordingArchive()
    source = CarSwitchSource("https://carswitch.test?page={page}", archive=archive)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        listings = await source._get_page_with_retry(client, "https://carswitch.test?page=1")

    assert attempts == 1
    assert len(archive.payloads) == 1
    assert archive.attempt_numbers == [1]
    assert sleeps == []
    assert len(listings) == 1


@pytest.mark.asyncio
async def test_identical_empty_attempts_keep_three_capture_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def no_wait(seconds: float) -> None:
        assert seconds in {1, 2}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"",
            headers={"content-type": "text/html"},
            request=request,
        )

    monkeypatch.setattr("src.sources.carswitch.asyncio.sleep", no_wait)
    repository = LocalRepository(tmp_path / "raw-attempts.db")
    archive = LocalRawSnapshotArchive(tmp_path / "raw", repository)
    source = CarSwitchSource("https://carswitch.test?page={page}", archive=archive)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceError):
            await source._get_page_with_retry(client, "https://carswitch.test?page=1")

    events = [
        event
        for event in reversed(repository.list_audit_events(limit=10))
        if event["event_type"] == "raw_snapshot_attempt"
    ]
    assert [event["payload"]["attempt_number"] for event in events] == [1, 2, 3]
    assert len({event["payload"]["storage_uri"] for event in events}) == 1
    assert len(list((tmp_path / "raw").rglob("*.*"))) == 1


def test_parser_rejects_monthly_and_missing_purchase_price() -> None:
    monthly = VALID_HTML.replace(
        '"price": "79000", "priceCurrency": "AED"',
        '"price": "999", "priceCurrency": "AED", "unitText": "monthly"',
    )
    missing = VALID_HTML.replace(
        '"offers": {"price": "79000", "priceCurrency": "AED"}',
        '"offers": {"priceCurrency": "AED"}',
    )

    assert parse_carswitch_page(monthly) == []
    assert parse_carswitch_page(missing) == []


class FailingSource:
    """Имитирует исчерпанный semantic retry для проверки health evidence."""

    async def fetch(self) -> list[ListingSnapshot]:
        raise SourceError(
            "semantic transient exhausted",
            category=SEMANTIC_EMPTY_RESPONSE,
            attempts=3,
        )


@pytest.mark.asyncio
async def test_source_run_records_terminal_semantic_category(tmp_path: Path) -> None:
    settings = replace(
        Settings.from_env(),
        storage_backend="local",
        database_path=tmp_path / "carswitch-health.db",
    )
    repository = LocalRepository(settings.database_path)
    service = DealService(settings, repository, {"carswitch": FailingSource()})

    with pytest.raises(SourceError):
        await service.collect("carswitch")

    health = repository.source_health()["carswitch"]
    assert health["success"] is False
    assert health["error_category"] == SEMANTIC_EMPTY_RESPONSE
    assert health["attempts"] == 3
    assert repository.count_snapshots() == 0
    assert repository.latest_decisions() == []

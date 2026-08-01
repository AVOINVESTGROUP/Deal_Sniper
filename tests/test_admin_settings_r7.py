"""Сквозные API-контракты управляемой монетизации R7."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from src.auth import Principal
from src.storage import LocalRepository


@pytest.mark.asyncio
async def test_admin_can_preview_apply_and_replay_price_change_without_second_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "admin-r7.db")
    fake_service = SimpleNamespace(repository=repository)
    monkeypatch.setattr(web, "service", fake_service)
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(
            subject="owner", email="owner@example.com", admin=require_admin
        ),
    )
    created: list[dict[str, Any]] = []

    async def fake_create_link(
        _settings: object,
        *,
        price_stars: int,
        name: str,
    ) -> str:
        created.append({"price_stars": price_stars, "name": name})
        return "https://t.me/+r7-paid-link"

    monkeypatch.setattr(web, "create_telegram_subscription_link", fake_create_link)
    payload = {
        "pro_price_aed": 125,
        "pro_price_stars": 1800,
        "target_profit_aed": "7000",
        "min_roi_percent": "12.5",
        "min_comparables_count": 6,
        "channel_max_posts_per_run": 8,
        "operation_id": "operation-r7-price-1",
        "confirmation": "",
    }
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preview = await client.post("/admin/settings/preview", json=payload)
        assert preview.status_code == 200
        assert preview.json()["confirmation_required"] == "APPLY 1800 STARS"

        payload["confirmation"] = "APPLY 1800 STARS"
        applied = await client.post("/admin/settings/apply", json=payload)
        replayed = await client.post("/admin/settings/apply", json=payload)
        current = await client.get("/admin/settings")

    assert applied.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json()["replayed"] is True
    assert len(created) == 1
    assert current.json()["active"]["pro_price_aed"] == 125
    assert current.json()["active"]["pro_price_stars"] == 1800
    assert current.json()["active"]["pro_subscription_url"] != "https://t.me/+r7-paid-link"


@pytest.mark.asyncio
async def test_admin_apply_rejects_missing_exact_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    monkeypatch.setattr(
        web,
        "service",
        SimpleNamespace(repository=LocalRepository(tmp_path / "x.db")),
    )
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(subject="owner", admin=require_admin),
    )
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/admin/settings/apply",
            json={
                "pro_price_aed": 100,
                "pro_price_stars": 1500,
                "target_profit_aed": 5000,
                "min_roi_percent": 10,
                "min_comparables_count": 5,
                "channel_max_posts_per_run": 10,
                "operation_id": "operation-r7-invalid",
                "confirmation": "yes",
            },
        )
    assert response.status_code == 422
    assert "APPLY 1500 STARS" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_scheduler_action_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "scheduler-r7.db")
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(
            subject="owner", email="owner@example.com", admin=require_admin
        ),
    )
    calls: list[str] = []

    def fake_scheduler_action(
        _project: str, _region: str, job_name: str, action: str
    ) -> dict[str, Any]:
        calls.append(f"{action}:{job_name}")
        return {"name": job_name, "state": "RUNNING", "action": action}

    monkeypatch.setattr(web, "scheduler_action", fake_scheduler_action)
    payload = {
        "action": "run",
        "operation_id": "scheduler-operation-r7",
        "confirmation": "RUN deal-sniper-dubicars-every-10m",
    }
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/admin/schedulers/deal-sniper-dubicars-every-10m/action", json=payload
        )
        replay = await client.post(
            "/admin/schedulers/deal-sniper-dubicars-every-10m/action", json=payload
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert calls == ["run:deal-sniper-dubicars-every-10m"]


@pytest.mark.asyncio
async def test_admin_rollback_replay_does_not_create_second_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src import web

    repository = LocalRepository(tmp_path / "rollback-r7.db")
    monkeypatch.setattr(web, "service", SimpleNamespace(repository=repository))
    monkeypatch.setattr(
        web,
        "firebase_principal",
        lambda _authorization, *, require_admin: Principal(
            subject="owner", email="owner@example.com", admin=require_admin
        ),
    )
    created: list[int] = []

    async def fake_create_link(
        _settings: object,
        *,
        price_stars: int,
        name: str,
    ) -> str:
        del name
        created.append(price_stars)
        return f"https://t.me/+r7-{price_stars}-{len(created)}"

    monkeypatch.setattr(web, "create_telegram_subscription_link", fake_create_link)
    base_payload = {
        "pro_price_aed": 125,
        "pro_price_stars": 1800,
        "target_profit_aed": "7000",
        "min_roi_percent": "12.5",
        "min_comparables_count": 6,
        "channel_max_posts_per_run": 8,
        "operation_id": "rollback-seed-r7",
        "confirmation": "APPLY 1800 STARS",
    }
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        seeded = await client.post("/admin/settings/apply", json=base_payload)
        version = seeded.json()["active"]["version"]
        rollback_payload = {
            "version": version,
            "operation_id": "rollback-operation-r7",
            "confirmation": f"ROLLBACK {version}",
        }
        first = await client.post("/admin/settings/rollback", json=rollback_payload)
        replay = await client.post("/admin/settings/rollback", json=rollback_payload)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert created == [1800, 1800]

"""Состояние и allowlisted-управление Cloud runtime из Admin Web."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

SCHEDULER_ACTIONS = frozenset({"run", "pause", "resume"})


def cloud_runtime_status(project_id: str, region: str) -> dict[str, Any]:
    # OAuth scope разрешает запросить API, а фактические полномочия всё равно
    # ограничены viewer-ролями service account на уровне IAM.
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    scheduler_url = (
        f"https://cloudscheduler.googleapis.com/v1/projects/{project_id}/locations/{region}/jobs"
    )
    queues_url = (
        f"https://cloudtasks.googleapis.com/v2/projects/{project_id}/locations/{region}/queues"
    )
    run_url = f"https://run.googleapis.com/v2/projects/{project_id}/locations/{region}/services"
    requests = {
        "scheduler": (scheduler_url, "jobs", ("name", "state", "schedule")),
        "queues": (queues_url, "queues", ("name", "state")),
        "services": (run_url, "services", ("name", "latestReadyRevision", "traffic")),
    }
    # Последовательные тайм-ауты трёх Cloud API превышали лимит API Gateway.
    # Отдельная сессия на компонент исключает совместное состояние requests.Session.
    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        futures = {
            name: executor.submit(
                _get_items,
                _authorized_session(credentials, project_id),
                url,
                key,
                fields,
            )
            for name, (url, key, fields) in requests.items()
        }
        return {name: future.result() for name, future in futures.items()}


def _authorized_session(credentials: Any, project_id: str) -> AuthorizedSession:
    """Создаёт изолированную Cloud API session с явным quota project."""
    session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
    session.headers["x-goog-user-project"] = project_id
    return session


def _get_items(
    session: AuthorizedSession,
    url: str,
    key: str,
    allowed_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    response = session.get(url, timeout=8)
    if not response.ok:
        return [{"state": "UNAVAILABLE", "http_status": response.status_code}]
    payload = response.json()
    return [
        {field: item.get(field) for field in allowed_fields}
        for item in payload.get(key, [])
        if isinstance(item, dict)
    ]


def scheduler_action(project_id: str, region: str, job_name: str, action: str) -> dict[str, Any]:
    """Выполняет ограниченное действие только над ресурсами Deal Sniper."""
    if action not in SCHEDULER_ACTIONS:
        raise ValueError("Разрешены только run, pause и resume")
    if (
        not job_name.startswith("deal-sniper-")
        or len(job_name) > 63
        or not all(char.islower() or char.isdigit() or char == "-" for char in job_name)
    ):
        raise ValueError("Scheduler job не входит в allowlist Deal Sniper")
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = _authorized_session(credentials, project_id)
    url = (
        f"https://cloudscheduler.googleapis.com/v1/projects/{project_id}/locations/"
        f"{region}/jobs/{job_name}:{action}"
    )
    response = session.post(url, json={}, timeout=15)
    if not response.ok:
        raise RuntimeError(f"Cloud Scheduler отклонил действие: HTTP {response.status_code}")
    payload = response.json()
    return {
        "name": payload.get("name", job_name),
        "state": payload.get("state", "UNKNOWN"),
        "action": action,
    }

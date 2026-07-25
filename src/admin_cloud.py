"""Read-only состояние Scheduler, Cloud Tasks и Cloud Run для admin panel."""

from __future__ import annotations

from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession


def cloud_runtime_status(project_id: str, region: str) -> dict[str, Any]:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform.read-only"]
    )
    session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
    scheduler_url = (
        f"https://cloudscheduler.googleapis.com/v1/projects/{project_id}/"
        f"locations/{region}/jobs"
    )
    queues_url = (
        f"https://cloudtasks.googleapis.com/v2/projects/{project_id}/"
        f"locations/{region}/queues"
    )
    run_url = (
        f"https://run.googleapis.com/v2/projects/{project_id}/locations/{region}/services"
    )
    return {
        "scheduler": _get_items(session, scheduler_url, "jobs", ("name", "state", "schedule")),
        "queues": _get_items(session, queues_url, "queues", ("name", "state")),
        "services": _get_items(
            session,
            run_url,
            "services",
            ("name", "latestReadyRevision", "traffic"),
        ),
    }


def _get_items(
    session: AuthorizedSession,
    url: str,
    key: str,
    allowed_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return [
        {field: item.get(field) for field in allowed_fields}
        for item in payload.get(key, [])
        if isinstance(item, dict)
    ]

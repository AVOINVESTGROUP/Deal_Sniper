"""Защита выбора Cloud Run Job для ручной Pro-публикации."""

from __future__ import annotations

import pytest

from src.admin_cloud import run_publisher_job


def test_publisher_job_rejects_name_outside_exact_allowlist() -> None:
    with pytest.raises(ValueError, match="точный allowlist"):
        run_publisher_job("project", "region", "deal-sniper-collector")

"""Статические контракты восстановления регулярного контура R8.1.3."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_collectors_are_staggered_every_ten_minutes() -> None:
    variables = (ROOT / "infra" / "terraform" / "variables.tf").read_text(encoding="utf-8")

    for schedule in (
        "0,10,20,30,40,50 * * * *",
        "2,12,22,32,42,52 * * * *",
        "4,14,24,34,44,54 * * * *",
        "6,16,26,36,46,56 * * * *",
    ):
        assert schedule in variables


def test_deal_publisher_is_managed_and_runs_every_fifteen_minutes() -> None:
    terraform = (ROOT / "infra" / "terraform" / "main.tf").read_text(encoding="utf-8")
    entrypoint = (ROOT / "main.py").read_text(encoding="utf-8")

    assert 'name     = "deal-sniper-publisher"' in terraform
    assert 'args    = ["main.py", "publish"]' in terraform
    assert 'schedule         = "3,18,33,48 * * * *"' in terraform
    assert 'DELIVERY_ENABLED             = "true"' in terraform
    assert 'elif args.command == "publish":' in entrypoint


def test_processing_queue_limits_detail_verification_pressure() -> None:
    terraform = (ROOT / "infra" / "terraform" / "main.tf").read_text(encoding="utf-8")
    processing = terraform.split(
        'resource "google_cloud_tasks_queue" "processing"', maxsplit=1
    )[1].split('resource "google_cloud_tasks_queue" "delivery"', maxsplit=1)[0]

    assert "max_concurrent_dispatches = 2" in processing
    assert "max_dispatches_per_second = 2" in processing

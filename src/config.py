"""Типизированная конфигурация приложения из переменных окружения."""

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _integer_set(value: str) -> frozenset[int]:
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Настройки локального MVP и Telegram-интерфейса."""

    telegram_bot_token: str
    telegram_allowed_user_ids: frozenset[int]
    telegram_channel_id: str | None
    telegram_webhook_secret: str
    google_cloud_project: str
    google_cloud_region: str
    raw_snapshots_bucket: str
    cloud_run_api_url: str
    cloud_tasks_location: str
    listing_processing_queue: str
    telegram_delivery_queue: str
    task_invoker_service_account: str
    internal_task_secret: str
    collector_job_prefix: str
    storage_backend: str
    database_path: Path
    local_raw_snapshots_path: Path
    source_url_template: str
    source_pages: int
    carswitch_url_template: str
    carswitch_pages: int
    cars24_url_template: str
    cars24_pages: int
    opensooq_url_template: str
    opensooq_pages: int
    request_timeout_seconds: float
    target_profit_aed: Decimal
    min_roi_percent: Decimal
    min_comparables_count: int
    default_cost_aed: Decimal
    channel_max_posts_per_run: int
    inspection_cost_aed: Decimal
    preparation_cost_aed: Decimal
    base_repair_reserve_aed: Decimal
    holding_cost_per_day_aed: Decimal
    expected_hold_days: int
    annual_capital_percent: Decimal
    selling_cost_percent: Decimal
    risk_reserve_percent: Decimal
    aed_to_usd_rate: Decimal

    @classmethod
    def from_env(cls) -> "Settings":
        """Создаёт конфигурацию без неявных секретов и mock-режима."""
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_user_ids=_integer_set(os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")),
            telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID") or None,
            telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip(),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            google_cloud_region=os.getenv("GOOGLE_CLOUD_REGION", "me-central1").strip(),
            raw_snapshots_bucket=os.getenv("RAW_SNAPSHOTS_BUCKET", "").strip(),
            cloud_run_api_url=os.getenv("CLOUD_RUN_API_URL", "").rstrip("/"),
            cloud_tasks_location=os.getenv("CLOUD_TASKS_LOCATION", "").strip(),
            listing_processing_queue=os.getenv(
                "LISTING_PROCESSING_QUEUE", "listing-processing"
            ).strip(),
            telegram_delivery_queue=os.getenv(
                "TELEGRAM_DELIVERY_QUEUE", "telegram-delivery"
            ).strip(),
            task_invoker_service_account=os.getenv(
                "TASK_INVOKER_SERVICE_ACCOUNT", ""
            ).strip(),
            internal_task_secret=os.getenv("INTERNAL_TASK_SECRET", "").strip(),
            collector_job_prefix=os.getenv(
                "COLLECTOR_JOB_PREFIX", "deal-sniper-collector"
            ).strip(),
            storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
            database_path=Path(os.getenv("LOCAL_DATABASE_PATH", "data/deal_sniper.db")),
            local_raw_snapshots_path=Path(
                os.getenv("LOCAL_RAW_SNAPSHOTS_PATH", "data/raw")
            ),
            source_url_template=os.getenv(
                "DUBICARS_URL_TEMPLATE",
                "https://www.dubicars.com/uae/used?page={page}",
            ),
            source_pages=max(1, int(os.getenv("DUBICARS_MAX_PAGES", "3"))),
            carswitch_url_template=os.getenv(
                "CARSWITCH_URL_TEMPLATE",
                "https://carswitch.com/dubai/used-cars/search?page={page}",
            ),
            carswitch_pages=max(1, int(os.getenv("CARSWITCH_MAX_PAGES", "3"))),
            cars24_url_template=os.getenv(
                "CARS24_URL_TEMPLATE",
                "https://www.cars24.ae/buy-used-cars-dubai/?page={page}",
            ),
            cars24_pages=max(1, int(os.getenv("CARS24_MAX_PAGES", "3"))),
            opensooq_url_template=os.getenv(
                "OPENSOOQ_URL_TEMPLATE",
                "https://ae.opensooq.com/en/cars/cars-for-sale?sort=recent&page={page}",
            ),
            opensooq_pages=max(1, int(os.getenv("OPENSOOQ_MAX_PAGES", "5"))),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            target_profit_aed=Decimal(os.getenv("TARGET_PROFIT_AED", "5000")),
            min_roi_percent=Decimal(os.getenv("MIN_ROI_PERCENT", "10")),
            min_comparables_count=max(2, int(os.getenv("MIN_COMPARABLES_COUNT", "3"))),
            default_cost_aed=Decimal(os.getenv("DEFAULT_NON_PURCHASE_COST_AED", "5000")),
            channel_max_posts_per_run=max(
                1,
                int(os.getenv("CHANNEL_MAX_POSTS_PER_RUN", "10")),
            ),
            inspection_cost_aed=Decimal(os.getenv("INSPECTION_COST_AED", "500")),
            preparation_cost_aed=Decimal(os.getenv("PREPARATION_COST_AED", "1500")),
            base_repair_reserve_aed=Decimal(
                os.getenv("BASE_REPAIR_RESERVE_AED", "2500")
            ),
            holding_cost_per_day_aed=Decimal(
                os.getenv("HOLDING_COST_PER_DAY_AED", "50")
            ),
            expected_hold_days=max(1, int(os.getenv("EXPECTED_HOLD_DAYS", "45"))),
            annual_capital_percent=Decimal(os.getenv("ANNUAL_CAPITAL_PERCENT", "8")),
            selling_cost_percent=Decimal(os.getenv("SELLING_COST_PERCENT", "2")),
            risk_reserve_percent=Decimal(os.getenv("RISK_RESERVE_PERCENT", "5")),
            aed_to_usd_rate=Decimal(os.getenv("AED_TO_USD_RATE", "3.6725")),
        )

    def require_bot_token(self) -> str:
        """Возвращает токен либо останавливает запуск с понятной ошибкой."""
        if not self.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")
        return self.telegram_bot_token

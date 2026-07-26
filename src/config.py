"""Типизированная конфигурация приложения из переменных окружения."""

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _integer_set(value: str) -> frozenset[int]:
    return frozenset(int(item.strip()) for item in value.split(",") if item.strip())


def _string_set(value: str) -> frozenset[str]:
    return frozenset(item.strip().casefold() for item in value.split(",") if item.strip())


def _enabled(value: str) -> bool:
    """Fail-closed boolean: включено только явным значением true."""
    return value.strip().casefold() == "true"


def _rate(name: str, default: str, legacy_percent_name: str) -> Decimal:
    raw = os.getenv(name)
    if raw is not None:
        value = Decimal(raw)
    else:
        value = Decimal(os.getenv(legacy_percent_name, default)) / Decimal("100")
    if value < 0 or value > 1:
        raise ValueError(f"{name} должен быть долей 0..1")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Настройки локального MVP и Telegram-интерфейса."""

    telegram_bot_token: str
    telegram_allowed_user_ids: frozenset[int]
    telegram_admin_user_ids: frozenset[int]
    telegram_channel_id: str | None
    telegram_pro_channel_id: str | None
    telegram_pro_subscription_url: str
    telegram_webhook_secret: str
    google_cloud_project: str
    google_cloud_region: str
    firestore_database: str
    raw_snapshots_bucket: str
    cloud_run_api_url: str
    cloud_tasks_location: str
    listing_processing_queue: str
    telegram_delivery_queue: str
    task_invoker_service_account: str
    internal_task_secret: str
    delivery_enabled: bool
    admin_emails: frozenset[str]
    whatsapp_enabled: bool
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_api_version: str
    tma_url: str
    pro_price_aed: int
    pro_price_stars: int
    auto_news_rss_url: str
    auto_news_max_age_days: int
    auto_news_limit: int
    free_teaser_image_url: str
    schema_version: str
    migration_tool_version: str
    git_commit: str
    runtime_image_digest: str
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
    registration_cost_aed: Decimal
    preparation_cost_aed: Decimal
    repair_low_aed: Decimal
    repair_expected_aed: Decimal
    repair_high_aed: Decimal
    holding_cost_per_day_aed: Decimal
    expected_hold_days: int
    annual_capital_rate: Decimal
    selling_rate: Decimal
    risk_rate: Decimal
    liquidity_discount_rate: Decimal
    financial_config_version: str
    aed_to_usd_rate: Decimal

    @classmethod
    def from_env(cls) -> "Settings":
        """Создаёт конфигурацию без неявных секретов и mock-режима."""
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_user_ids=_integer_set(os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")),
            telegram_admin_user_ids=_integer_set(os.getenv("TELEGRAM_ADMIN_USER_IDS", "")),
            telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID") or None,
            telegram_pro_channel_id=os.getenv("TELEGRAM_PRO_CHANNEL_ID") or None,
            telegram_pro_subscription_url=os.getenv("TELEGRAM_PRO_SUBSCRIPTION_URL", "").strip(),
            telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip(),
            google_cloud_project=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            google_cloud_region=os.getenv("GOOGLE_CLOUD_REGION", "me-central1").strip(),
            firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)").strip(),
            raw_snapshots_bucket=os.getenv("RAW_SNAPSHOTS_BUCKET", "").strip(),
            cloud_run_api_url=os.getenv("CLOUD_RUN_API_URL", "").rstrip("/"),
            cloud_tasks_location=os.getenv("CLOUD_TASKS_LOCATION", "").strip(),
            listing_processing_queue=os.getenv(
                "LISTING_PROCESSING_QUEUE", "listing-processing"
            ).strip(),
            telegram_delivery_queue=os.getenv(
                "TELEGRAM_DELIVERY_QUEUE", "telegram-delivery"
            ).strip(),
            task_invoker_service_account=os.getenv("TASK_INVOKER_SERVICE_ACCOUNT", "").strip(),
            internal_task_secret=os.getenv("INTERNAL_TASK_SECRET", "").strip(),
            delivery_enabled=_enabled(os.getenv("DELIVERY_ENABLED", "false")),
            admin_emails=_string_set(os.getenv("ADMIN_EMAILS", "")),
            whatsapp_enabled=_enabled(os.getenv("WHATSAPP_ENABLED", "false")),
            whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
            whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v23.0").strip(),
            tma_url=os.getenv("TMA_URL", "").strip(),
            pro_price_aed=max(1, int(os.getenv("PRO_PRICE_AED", "100"))),
            pro_price_stars=max(1, int(os.getenv("PRO_PRICE_STARS", "1500"))),
            auto_news_rss_url=os.getenv(
                "AUTO_NEWS_RSS_URL",
                "https://news.google.com/rss/search?q=%28Dubai%20OR%20UAE%29%20%28used%20cars%20OR%20automotive%20market%29&hl=en-AE&gl=AE&ceid=AE%3Aen",
            ).strip(),
            auto_news_max_age_days=max(1, int(os.getenv("AUTO_NEWS_MAX_AGE_DAYS", "45"))),
            auto_news_limit=max(1, min(5, int(os.getenv("AUTO_NEWS_LIMIT", "3")))),
            free_teaser_image_url=os.getenv("FREE_TEASER_IMAGE_URL", "").strip(),
            schema_version=os.getenv("SCHEMA_VERSION", "2").strip(),
            migration_tool_version=os.getenv("MIGRATION_TOOL_VERSION", "1.1.0").strip(),
            git_commit=os.getenv("GIT_COMMIT", "unknown").strip(),
            runtime_image_digest=os.getenv("RUNTIME_IMAGE_DIGEST", "unknown").strip(),
            collector_job_prefix=os.getenv("COLLECTOR_JOB_PREFIX", "deal-sniper-collector").strip(),
            storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
            database_path=Path(os.getenv("LOCAL_DATABASE_PATH", "data/deal_sniper.db")),
            local_raw_snapshots_path=Path(os.getenv("LOCAL_RAW_SNAPSHOTS_PATH", "data/raw")),
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
            registration_cost_aed=Decimal(os.getenv("REGISTRATION_COST_AED", "800")),
            preparation_cost_aed=Decimal(os.getenv("PREPARATION_COST_AED", "1500")),
            repair_low_aed=Decimal(os.getenv("REPAIR_LOW_AED", "1000")),
            repair_expected_aed=Decimal(os.getenv("REPAIR_EXPECTED_AED", "2500")),
            repair_high_aed=Decimal(os.getenv("REPAIR_HIGH_AED", "5000")),
            holding_cost_per_day_aed=Decimal(os.getenv("HOLDING_COST_PER_DAY_AED", "50")),
            expected_hold_days=max(1, int(os.getenv("EXPECTED_HOLD_DAYS", "45"))),
            annual_capital_rate=_rate("ANNUAL_CAPITAL_RATE", "8", "ANNUAL_CAPITAL_PERCENT"),
            selling_rate=_rate("SELLING_RATE", "2", "SELLING_COST_PERCENT"),
            risk_rate=_rate("RISK_RATE", "5", "RISK_RESERVE_PERCENT"),
            liquidity_discount_rate=_rate(
                "LIQUIDITY_DISCOUNT_RATE", "5", "LIQUIDITY_DISCOUNT_PERCENT"
            ),
            financial_config_version=os.getenv(
                "FINANCIAL_CONFIG_VERSION", "provisional-2026-07-v1"
            ).strip(),
            aed_to_usd_rate=Decimal(os.getenv("AED_TO_USD_RATE", "3.6725")),
        )

    def require_bot_token(self) -> str:
        """Возвращает токен либо останавливает запуск с понятной ошибкой."""
        if not self.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")
        return self.telegram_bot_token

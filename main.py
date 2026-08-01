"""Точки запуска Telegram-бота и однократного сканирования."""

import argparse
import asyncio
import logging
from datetime import UTC, datetime

from dotenv import load_dotenv

from src.bot import run_bot
from src.config import Settings
from src.service import DealService


def parse_args() -> argparse.Namespace:
    """Разбирает команду запуска."""
    parser = argparse.ArgumentParser(description="Dubai Deal Sniper")
    parser.add_argument(
        "command",
        choices=("bot", "scan", "collect", "publish", "content", "news", "replay"),
        help="Режим запуска",
    )
    parser.add_argument(
        "--source",
        help="Имя предустановленного или динамического источника",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Обработать migration replay напрямую без Cloud Tasks",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Повторить временно упавшие migration replay requests",
    )
    parser.add_argument(
        "--recalculate-all",
        action="store_true",
        help="Повторно рассчитать completed requests после наполнения verified market",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    return parser.parse_args()


async def scan_once(settings: Settings, source_name: str | None = None) -> None:
    """Выполняет один сбор и выводит результат в консоль."""
    service = DealService.from_settings(settings)
    report = await service.scan(source_name)
    print(report.summary())


async def collect_once(settings: Settings, source_name: str | None) -> None:
    """Collector Job сохраняет данные и ставит изменившиеся версии в Cloud Tasks."""
    if source_name is None:
        raise RuntimeError("Для collect обязателен параметр --source")
    from src.tasks import CloudTaskDispatcher

    service = DealService.from_settings(settings)
    report = await service.collect(source_name)
    dispatcher = CloudTaskDispatcher(settings)
    batch_id = datetime.now(UTC).strftime("%Y%m%d%H%M")
    await dispatcher.enqueue_processing_batch(
        report.pending,
        service.decision_engine.version,
        recalculation_epoch=f"{batch_id}-verify",
    )
    await dispatcher.enqueue_processing_batch(
        report.pending,
        service.decision_engine.version,
        recalculation_epoch=f"{batch_id}-market",
        delay_seconds=300,
    )
    print(report.summary())


def main() -> None:
    """Запускает выбранный режим приложения."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # HTTP-клиенты могут включать секретный Telegram-токен в полный URL запроса.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    args = parse_args()
    settings = Settings.from_env()
    if args.command == "bot":
        if not settings.delivery_enabled:
            raise RuntimeError("DELIVERY_ENABLED=false: Telegram long polling запрещён")
        run_bot(settings)
    elif args.command == "publish":
        from src.content_job import run_deal_publication

        pro, free = asyncio.run(run_deal_publication(settings))
        blocked = (
            free.blocked_no_pro
            + free.blocked_not_sent
            + free.blocked_revision_mismatch
        )
        print(
            f"Deals: Pro selected={pro.selected}, created={pro.created}, "
            f"requeued={pro.requeued}, skipped={pro.skipped}, failed={pro.failures}; "
            f"Free eligible={free.eligible}, created={free.created}, "
            f"requeued={free.requeued}, blocked={blocked}, "
            f"failed={free.failures}"
        )
    elif args.command == "content":
        from src.content_job import run_content_publication

        event_id, pro, news = asyncio.run(run_content_publication(settings))
        print(
            f"PublicationEvent: {event_id or 'channel-not-configured'}; "
            f"Pro: selected={pro.selected}, created={pro.created}, "
            f"requeued={pro.requeued}, skipped={pro.skipped}, failed={pro.failures}; "
            f"News: selected={news.selected}, created={news.created}, "
            f"requeued={news.requeued}, skipped={news.skipped}, failed={news.failures}"
        )
    elif args.command == "news":
        from src.content_job import run_news_publication

        news = asyncio.run(run_news_publication(settings))
        print(
            f"News: selected={news.selected}, created={news.created}, "
            f"requeued={news.requeued}, paired={news.paired_enqueued}, "
            f"blocked={news.blocked_pair}, failed={news.failures}"
        )
    elif args.command == "collect":
        asyncio.run(collect_once(settings, args.source))
    elif args.command == "replay":
        from src.replay import enqueue_migration_replay, run_migration_replay_direct

        if args.direct:
            report = asyncio.run(
                run_migration_replay_direct(
                    settings,
                    limit=args.limit,
                    concurrency=args.concurrency,
                    retry_failed=args.retry_failed,
                    recalculate_all=args.recalculate_all,
                    max_attempts=args.max_attempts,
                )
            )
        else:
            report = asyncio.run(enqueue_migration_replay(settings))
        print(
            f"Replay: pending={report.pending}; enqueued={report.enqueued}; "
            f"completed={report.completed}; failed={report.failed}; "
            f"skipped={report.skipped}"
        )
    else:
        asyncio.run(scan_once(settings, args.source))


if __name__ == "__main__":
    main()

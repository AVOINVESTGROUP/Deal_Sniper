"""Точки запуска Telegram-бота и однократного сканирования."""

import argparse
import asyncio
import logging

from dotenv import load_dotenv

from src.bot import run_bot, scan_and_publish
from src.config import Settings
from src.service import DealService


def parse_args() -> argparse.Namespace:
    """Разбирает команду запуска."""
    parser = argparse.ArgumentParser(description="Dubai Deal Sniper")
    parser.add_argument(
        "command",
        choices=("bot", "scan", "collect", "publish"),
        help="Режим запуска",
    )
    parser.add_argument("--source", choices=("dubicars", "carswitch", "cars24"))
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
    for listing_id, content_hash in report.pending:
        await dispatcher.enqueue_processing(
            listing_id,
            content_hash,
            service.decision_engine.version,
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
        run_bot(settings)
    elif args.command == "publish":
        sent = asyncio.run(scan_and_publish(settings))
        print(f"Опубликовано новых кандидатов: {sent}")
    elif args.command == "collect":
        asyncio.run(collect_once(settings, args.source))
    else:
        asyncio.run(scan_once(settings, args.source))


if __name__ == "__main__":
    main()

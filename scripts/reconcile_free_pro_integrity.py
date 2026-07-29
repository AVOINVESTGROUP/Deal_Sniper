"""Preview или удаление недоказуемых legacy Free-публикаций."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from telegram import Bot
from telegram.error import BadRequest

from src.config import Settings
from src.free_publication import legacy_free_integrity_items
from src.service import DealService


async def run(*, apply: bool) -> int:
    """По умолчанию ничего не меняет; apply удаляет только точные Telegram message IDs."""
    settings = Settings.from_env()
    service = DealService.from_settings(settings)
    items = await asyncio.to_thread(legacy_free_integrity_items, service.repository)
    unsafe = [item for item in items if item.classification != "matched"]
    report: dict[str, object] = {
        "mode": "apply" if apply else "preview",
        "total": len(items),
        "matched": sum(item.classification == "matched" for item in items),
        "unsafe": len(unsafe),
        "items": [asdict(item) for item in unsafe],
    }
    if not apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if not settings.telegram_channel_id:
        raise RuntimeError("TELEGRAM_CHANNEL_ID не настроен")
    deleted = already_absent = blocked = 0
    async with Bot(settings.require_bot_token()) as bot:
        for item in unsafe:
            if (
                item.recipient != settings.telegram_channel_id
                or not item.telegram_message_id
                or not item.telegram_message_id.isdigit()
            ):
                blocked += 1
                continue
            try:
                await bot.delete_message(item.recipient, int(item.telegram_message_id))
                outcome = "deleted"
                deleted += 1
            except BadRequest as error:
                if "message to delete not found" not in str(error).casefold():
                    raise
                outcome = "already_absent"
                already_absent += 1
            await asyncio.to_thread(
                service.repository.record_audit_event,
                "free_publication_withdrawn",
                {
                    "delivery_id": item.delivery_id,
                    "recipient": item.recipient,
                    "telegram_message_id": item.telegram_message_id,
                    "classification": item.classification,
                    "outcome": outcome,
                },
            )
    report.update({"deleted": deleted, "already_absent": already_absent, "blocked": blocked})
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if blocked == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())

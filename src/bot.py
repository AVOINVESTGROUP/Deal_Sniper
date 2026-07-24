"""Telegram-интерфейс локального MVP и публикация в канал."""

import html
import logging
from typing import Any

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from src.config import Settings
from src.domain.models import DealDecision, DecisionAction, ListingSnapshot
from src.service import DealService

logger = logging.getLogger(__name__)


def telegram_language(language_code: str | None) -> str:
    """Поддерживает русский интерфейс устройства, для остальных языков использует английский."""
    return "ru" if (language_code or "").casefold().startswith("ru") else "en"


def localized(language: str, russian: str, english: str) -> str:
    """Возвращает строку на поддерживаемом языке Telegram-пользователя."""
    return russian if telegram_language(language) == "ru" else english


def is_publishable(decision: DealDecision, settings: Settings) -> bool:
    """Защитный фильтр: убыточное решение никогда не уходит как кандидат."""
    return bool(
        decision.action in {DecisionAction.CONTACT, DecisionAction.INSPECT}
        and decision.expected_profit_aed is not None
        and decision.expected_profit_aed >= settings.target_profit_aed
        and decision.roi_percent is not None
        and decision.roi_percent >= settings.min_roi_percent
        and decision.max_purchase_price_aed is not None
        and decision.asking_price_aed <= decision.max_purchase_price_aed
    )


def select_publishable_decisions(
    decisions: list[tuple[ListingSnapshot, DealDecision]],
    settings: Settings,
    limit: int = 5,
) -> list[tuple[ListingSnapshot, DealDecision]]:
    """Выбирает лучшие актуальные решения без повторов одного объявления."""
    candidates = [item for item in decisions if is_publishable(item[1], settings)]
    candidates.sort(
        key=lambda item: (
            item[1].expected_profit_aed or 0,
            item[1].roi_percent or 0,
            item[1].confidence,
        ),
        reverse=True,
    )
    selected: list[tuple[ListingSnapshot, DealDecision]] = []
    seen_listing_ids: set[str] = set()
    for listing, decision in candidates:
        listing_id = f"{listing.source}:{listing.source_listing_id}"
        if listing_id in seen_listing_ids:
            continue
        seen_listing_ids.add(listing_id)
        selected.append((listing, decision))
        if len(selected) >= limit:
            break
    return selected


class DealBot:
    """Команды Telegram поверх независимого DealService."""

    def __init__(self, settings: Settings, service: DealService) -> None:
        self.settings = settings
        self.service = service

    def allowed(self, update: Update) -> bool:
        user = update.effective_user
        return bool(user and user.id in self.settings.telegram_allowed_user_ids)

    async def deny(self, update: Update) -> None:
        if update.effective_message:
            await update.effective_message.reply_text("Доступ к боту не настроен.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        await update.effective_message.reply_text(
            "Dubai Deal Sniper запущен.\n\n"
            "/scan — получить свежие объявления и выполнить расчёт\n"
            "/deals — показать последние подходящие варианты\n"
            "/status — состояние локального хранилища\n"
            "/sources — управление источниками"
        )

    async def identity(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает ID пользователя для первоначальной настройки allowlist."""
        del context
        user = update.effective_user
        if user and update.effective_message:
            await update.effective_message.reply_text(f"Ваш Telegram user ID: {user.id}")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        await update.effective_message.reply_text(
            f"Сохранено версий объявлений: {self.service.repository.count_snapshots()}"
        )

    async def scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        status_message = await update.effective_message.reply_text("Получаю свежие объявления…")
        try:
            report = await self.service.scan()
        except Exception:
            logger.exception("Ошибка сканирования")
            await status_message.edit_text(
                "Источник временно недоступен. Подробности записаны в лог."
            )
            return
        await status_message.edit_text(report.summary())
        candidates = [
            item for item in report.decisions if is_publishable(item.decision, self.settings)
        ][:5]
        for item in candidates:
            await update.effective_message.reply_text(
                format_card(item.listing, item.decision),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
        delivery_channel_id = (
            self.settings.telegram_pro_channel_id or self.settings.telegram_channel_id
        )
        if delivery_channel_id:
            await publish_candidates(
                update.get_bot(),
                delivery_channel_id,
                self.service,
                candidates,
            )

    async def deals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        decisions = self.service.repository.latest_decisions(limit=500)
        candidates = select_publishable_decisions(decisions, self.settings)
        if not candidates:
            await update.effective_message.reply_text("Подходящих вариантов пока нет.")
            return
        for listing, decision in candidates:
            await update.effective_message.reply_text(
                format_card(listing, decision),
                parse_mode=ParseMode.HTML,
            )

    async def sources_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает зарегистрированные площадки и команды управления ими."""
        del context
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        await update.effective_message.reply_text(format_sources(self.service))

    async def source_enable(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Включает зарегистрированный источник из Telegram."""
        await self._set_source(update, context, enabled=True)

    async def source_disable(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Отключает источник, сохраняя объявления и историю цен."""
        await self._set_source(update, context, enabled=False)

    async def _set_source(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        enabled: bool,
    ) -> None:
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        if not context.args:
            await update.effective_message.reply_text("Укажите источник. Пример: /source_on cars24")
            return
        try:
            self.service.set_source_enabled(context.args[0], enabled)
        except ValueError:
            await update.effective_message.reply_text(format_sources(self.service))
            return
        action = "включён" if enabled else "отключён"
        await update.effective_message.reply_text(
            f"Источник {context.args[0].casefold()} {action}.\n\n{format_sources(self.service)}"
        )

    async def source_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Проверяет один адаптер независимо от общего расписания."""
        if not self.allowed(update):
            await self.deny(update)
            return
        assert update.effective_message
        if not context.args:
            await update.effective_message.reply_text(
                "Укажите источник. Пример: /source_scan cars24"
            )
            return
        source_name = context.args[0].casefold()
        await update.effective_message.reply_text(f"Проверяю источник {source_name}…")
        try:
            report = await self.service.scan(source_name)
        except (RuntimeError, ValueError) as error:
            await update.effective_message.reply_text(f"Ошибка источника: {error}")
            return
        await update.effective_message.reply_text(f"{source_name}: {report.summary()}")


def format_card(
    listing: ListingSnapshot,
    decision: DealDecision,
    language: str = "ru",
) -> str:
    """Создаёт безопасную HTML-карточку решения."""
    market = decision.market
    market_text = (
        f"{market.low_aed:,.0f}–{market.high_aed:,.0f} AED"
        if market
        else localized(language, "недостаточно данных", "insufficient data")
    )
    profit = (
        f"{decision.expected_profit_aed:,.0f} AED"
        if decision.expected_profit_aed is not None
        else "—"
    )
    roi = f"{decision.roi_percent}%" if decision.roi_percent is not None else "—"
    listing_id = f"{listing.source}:{listing.source_listing_id}"
    return (
        f"<b>{html.escape(decision.action.value)}</b>\n"
        f"<b>{html.escape(listing.title)}</b>\n"
        f"{localized(language, 'Цена', 'Price')}: <b>{listing.price_aed:,.0f} AED</b>\n"
        f"{localized(language, 'Рынок', 'Market')}: {market_text}\n"
        f"{localized(language, 'Ожидаемая прибыль', 'Expected profit')}: {profit}\n"
        f"ROI: {roi}\n"
        f"{localized(language, 'Уверенность', 'Confidence')}: {decision.confidence:.0%}\n"
        f'<a href="{html.escape(str(listing.url), quote=True)}">'
        f"{localized(language, 'Открыть объявление', 'Open listing')}</a>\n"
        f"ID: <code>{html.escape(listing_id)}</code>\n"
        f"/watch {html.escape(listing_id)}"
    )


def format_sources(service: DealService, language: str = "ru") -> str:
    """Формирует понятную панель управления источниками и их здоровьем."""
    statuses = service.source_statuses()
    health = service.repository.source_health()
    enabled_count = sum(statuses.values())
    lines = [
        localized(
            language,
            f"Источники: {len(statuses)}. Включено: {enabled_count}.",
            f"Sources: {len(statuses)}. Enabled: {enabled_count}.",
        ),
        "",
    ]
    for name, enabled in statuses.items():
        source_run = health.get(name, {})
        if not enabled:
            lines.append(f"⛔ {name}: {localized(language, 'отключён', 'disabled')}")
            continue
        success = source_run.get("success")
        mark = "✅" if success is True else "⚠️" if success is False else "⏳"
        fetched = source_run.get("fetched")
        details = (
            localized(
                language,
                f"последний сбор {fetched} авто",
                f"last scan: {fetched} cars",
            )
            if isinstance(fetched, int)
            else localized(language, "ещё не запускался", "not scanned yet")
        )
        lines.append(f"{mark} {name}: {details}")
    lines.extend(
        [
            "",
            localized(
                language,
                "Управление (замените имя источника):",
                "Management (replace the source name):",
            ),
            localized(
                language,
                "/source_scan opensooq — запустить отдельно",
                "/source_scan opensooq — run separately",
            ),
            localized(
                language, "/source_off opensooq — отключить", "/source_off opensooq — disable"
            ),
            localized(language, "/source_on opensooq — включить", "/source_on opensooq — enable"),
            localized(
                language, "/scan — запустить все включённые", "/scan — run all enabled sources"
            ),
        ]
    )
    return "\n".join(lines)


def build_application(settings: Settings) -> Application[Any, Any, Any, Any, Any, Any]:
    """Собирает Telegram Application для тестирования и запуска."""
    service = DealService.from_settings(settings)
    bot = DealBot(settings, service)
    application = ApplicationBuilder().token(settings.require_bot_token()).build()
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.start))
    application.add_handler(CommandHandler("id", bot.identity))
    application.add_handler(CommandHandler("status", bot.status))
    application.add_handler(CommandHandler("scan", bot.scan))
    application.add_handler(CommandHandler("deals", bot.deals))
    application.add_handler(CommandHandler("sources", bot.sources_status))
    application.add_handler(CommandHandler(("source_on", "source_add"), bot.source_enable))
    application.add_handler(CommandHandler(("source_off", "source_remove"), bot.source_disable))
    application.add_handler(CommandHandler("source_scan", bot.source_scan))
    return application


def run_bot(settings: Settings) -> None:
    """Запускает long polling с корректным завершением библиотеки."""
    build_application(settings).run_polling(drop_pending_updates=False)


async def scan_and_publish(settings: Settings) -> int:
    """Однократно сканирует источник и публикует новые кандидаты в канал."""
    channel_id = settings.telegram_pro_channel_id or settings.telegram_channel_id
    if not channel_id:
        raise RuntimeError("TELEGRAM_PRO_CHANNEL_ID или TELEGRAM_CHANNEL_ID не задан в .env")
    service = DealService.from_settings(settings)
    report = await service.scan()
    candidates = [item for item in report.decisions if is_publishable(item.decision, settings)]
    candidates.sort(
        key=lambda item: (
            item.decision.expected_profit_aed or 0,
            item.decision.roi_percent or 0,
            item.decision.confidence,
        ),
        reverse=True,
    )
    candidates = candidates[: settings.channel_max_posts_per_run]
    async with Bot(settings.require_bot_token()) as bot:
        return await publish_candidates(bot, channel_id, service, candidates)


async def publish_candidates(
    bot: Bot,
    target_id: str,
    service: DealService,
    candidates: list[Any],
) -> int:
    """Публикует только ещё не доставленные версии объявлений."""
    sent = 0
    for item in candidates:
        listing_id = f"{item.listing.source}:{item.listing.source_listing_id}"
        if service.repository.notification_sent(target_id, listing_id, item.content_hash):
            continue
        await bot.send_message(
            chat_id=target_id,
            text=format_card(item.listing, item.decision, language="en"),
            parse_mode=ParseMode.HTML,
        )
        service.repository.mark_notification_sent(target_id, listing_id, item.content_hash)
        sent += 1
    return sent

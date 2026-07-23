import os
import asyncio
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DubaiDealSniper")

from src.db import DealDatabase
from src.evaluator import GeminiEvaluator
from src.notifier import TelegramNotifier
from src.scrapers.base_scraper import BaseScraper
from src.scrapers.dubizzle_mock import DubizzleMockScraper

async def run_pipeline(
    db: DealDatabase,
    evaluator: GeminiEvaluator,
    notifier: TelegramNotifier,
    scrapers: list[BaseScraper],
) -> None:
    """Один цикл работы конвейера сбора и оценки объявлений."""
    logger.info("Начало проверки объявлений...")
    min_discount = float(os.getenv("MIN_DISCOUNT_PERCENT", "15"))
    
    for scraper in scrapers:
        scraper_name = scraper.__class__.__name__
        try:
            listings = await scraper.fetch_listings()
            logger.info(f"Скрапер {scraper_name} вернул {len(listings)} объявлений.")
            
            for item in listings:
                if db.is_seen(item.url):
                    # Объявление уже обрабатывалось, пропускаем
                    continue
                
                logger.info(f"Новое объявление обнаружено: {item.title} ({item.price} AED). Начинаем оценку...")
                
                try:
                    # Оценка с помощью ИИ
                    evaluation = await evaluator.evaluate_listing(item)
                    logger.info(
                        f"Оценка завершена: Сделка={evaluation.is_deal}, "
                        f"Дисконт={evaluation.discount_percent}%, Оценка={evaluation.deal_score}/10"
                    )
                    
                    # Решаем, отправлять ли уведомление
                    should_alert = evaluation.is_deal or (evaluation.discount_percent >= min_discount)
                    alert_sent = False
                    
                    if should_alert:
                        alert_sent = await notifier.send_deal_alert(item, evaluation)
                    
                    # Сохраняем в БД дедупликации
                    db.add_seen(
                        url=item.url,
                        is_deal=evaluation.is_deal,
                        deal_score=evaluation.deal_score,
                        alert_sent=alert_sent
                    )
                except Exception as eval_err:
                    logger.error(f"Ошибка при оценке объявления {item.url}: {eval_err}", exc_info=True)
                    
        except Exception as scrap_err:
            logger.error(f"Ошибка работы скрапера {scraper_name}: {scrap_err}", exc_info=True)

async def main() -> None:
    logger.info("Запуск сервиса Dubai Deal Sniper MVP...")
    
    # Инициализация модулей
    db = DealDatabase("data/deals.db")
    
    # Если ключ API отсутствует, сообщаем пользователю
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("Критическая ошибка: GEMINI_API_KEY не задан в .env файле.")
        return
        
    evaluator = GeminiEvaluator()
    notifier = TelegramNotifier()
    
    scrapers = [
        DubizzleMockScraper()
    ]
    
    check_interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    
    while True:
        try:
            await run_pipeline(db, evaluator, notifier, scrapers)
        except Exception as e:
            logger.critical(f"Непредвиденная ошибка в основном цикле: {e}", exc_info=True)
        
        logger.info(f"Ожидание следующей проверки {check_interval} сек...")
        await asyncio.sleep(check_interval)

if __name__ == "__main__":
    asyncio.run(main())

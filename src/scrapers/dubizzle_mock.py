from typing import List
from src.scrapers.base_scraper import BaseScraper
from src.models import ListingItem

class DubizzleMockScraper(BaseScraper):
    """Скрапер-заглушка для Dubizzle (для безопасной демонстрации и тестов)."""
    
    async def fetch_listings(self) -> List[ListingItem]:
        # Возвращает качественные мок-данные для Dubizzle
        return [
            ListingItem(
                title="Mercedes-Benz G63 AMG 2020",
                price=380000.0,
                location="Dubai, Marina",
                source="Dubizzle",
                url="https://dubai.dubizzle.com/motors/used-cars/mercedes-benz/g-class/2020/g63-amg-12345/",
                raw_description="Срочная продажа! Отличное состояние, пробег 45 000 км. Без ДТП, обслуживался у официального дилера. Владелец уезжает из страны, поэтому цена снижена.",
                image_urls=["https://images.dubizzle.com/placeholder_g63.jpg"],
                vin="WDBYG7EX0L246810"
            ),
            ListingItem(
                title="Tesla Model 3 2022 Performance",
                price=95000.0,
                location="Dubai, Downtown",
                source="Dubizzle",
                url="https://dubai.dubizzle.com/motors/used-cars/tesla/model-3/2022/performance-54321/",
                raw_description="Небольшая вмятина на задней правой двери. Батарея 92% здоровья. Требуется локальный ремонт двери и полировка кузова.",
                image_urls=["https://images.dubizzle.com/placeholder_tesla.jpg"],
                vin="5YJ3E1EA5NF123456"
            )
        ]

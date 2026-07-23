from abc import ABC, abstractmethod
from typing import List
from src.models import ListingItem

class BaseScraper(ABC):
    """Абстрактный класс для всех скраперов (Dubai Deal Sniper)."""
    
    @abstractmethod
    async def fetch_listings(self) -> List[ListingItem]:
        """
        Асинхронно сканирует источник и возвращает список элементов ListingItem.
        """
        pass

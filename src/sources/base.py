"""Контракт источника объявлений."""

from typing import Protocol

from src.domain.models import ListingSnapshot


class SourceAdapter(Protocol):
    """Единый интерфейс независимо реализуемого источника."""

    async def fetch(self) -> list[ListingSnapshot]:
        """Получает текущие объявления без скрытого mock fallback."""
        ...

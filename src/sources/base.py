"""Контракт источника объявлений."""

import logging
from typing import Protocol

from src.domain.models import ListingSnapshot

logger = logging.getLogger(__name__)


class SourceAdapter(Protocol):
    """Единый интерфейс независимо реализуемого источника."""

    async def fetch(self) -> list[ListingSnapshot]:
        """Получает текущие объявления без скрытого mock fallback."""
        ...


class CompositeSource:
    """Объединяет независимые реальные адаптеры и изолирует их сбои."""

    def __init__(self, sources: list[SourceAdapter]) -> None:
        self.sources = sources

    async def fetch(self) -> list[ListingSnapshot]:
        results: dict[tuple[str, str], ListingSnapshot] = {}
        errors: list[str] = []
        for source in self.sources:
            try:
                for listing in await source.fetch():
                    results[(listing.source, listing.source_listing_id)] = listing
            except Exception as error:
                logger.warning("Источник временно пропущен: %s", error)
                errors.append(str(error))
        if not results:
            raise RuntimeError("Все реальные источники недоступны: " + "; ".join(errors))
        return list(results.values())

"""Оркестрация сбора, истории и детерминированного решения."""

from dataclasses import dataclass, field
from decimal import Decimal

from src.config import Settings
from src.domain.engines import ComparablePriceEngine, DecisionEngine, DecisionPolicy
from src.domain.models import ComparableVehicle, CostEstimate, DealDecision, ListingSnapshot
from src.sources.dubicars import DubiCarsSource
from src.storage import LocalRepository


@dataclass(slots=True)
class EvaluatedListing:
    """Объявление, его версия и рассчитанное решение."""

    listing: ListingSnapshot
    content_hash: str
    decision: DealDecision


@dataclass(slots=True)
class ScanReport:
    """Результат одного запуска реального collector."""

    fetched: int = 0
    new: int = 0
    changed: int = 0
    decisions: list[EvaluatedListing] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Получено: {self.fetched}; новых: {self.new}; "
            f"изменений цены: {self.changed}; решений: {len(self.decisions)}"
        )


class DealService:
    """Прикладной сервис без зависимости от Telegram."""

    def __init__(
        self,
        settings: Settings,
        repository: LocalRepository,
        source: DubiCarsSource,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.source = source
        self.market_engine = ComparablePriceEngine()
        self.decision_engine = DecisionEngine(
            DecisionPolicy(
                target_profit_aed=settings.target_profit_aed,
                min_roi_percent=settings.min_roi_percent,
                min_comparables=settings.min_comparables_count,
            )
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "DealService":
        return cls(
            settings=settings,
            repository=LocalRepository(settings.database_path),
            source=DubiCarsSource(
                settings.source_url_template,
                pages=settings.source_pages,
                timeout_seconds=settings.request_timeout_seconds,
            ),
        )

    async def scan(self) -> ScanReport:
        """Собирает источник, сохраняет версии и рассчитывает доступные группы."""
        fetched = await self.source.fetch()
        report = ScanReport(fetched=len(fetched))
        version_hashes: dict[str, str] = {}
        for listing in fetched:
            is_new, price_changed, content_hash = self.repository.save_snapshot(listing)
            report.new += int(is_new)
            report.changed += int(price_changed)
            version_hashes[f"{listing.source}:{listing.source_listing_id}"] = content_hash

        current = self.repository.latest_snapshots()
        groups: dict[tuple[str, str], list[ListingSnapshot]] = {}
        for listing in current:
            if listing.make and listing.model and listing.year and listing.mileage_km is not None:
                groups.setdefault((listing.make.casefold(), listing.model.casefold()), []).append(
                    listing
                )

        for listings in groups.values():
            comparables = [self._as_comparable(item) for item in listings]
            for listing in listings:
                peers = [
                    item for item in comparables if item.listing_id != listing.source_listing_id
                ]
                market = self.market_engine.estimate(
                    peers,
                    min_comparables=self.settings.min_comparables_count,
                )
                decision = self.decision_engine.decide(
                    asking_price_aed=listing.price_aed,
                    market=market,
                    costs=CostEstimate(
                        preparation_aed=self.settings.default_cost_aed,
                        risk_reserve_aed=money_percent(listing.price_aed, Decimal("5")),
                    ),
                )
                listing_id = f"{listing.source}:{listing.source_listing_id}"
                decision_hash = version_hashes.get(listing_id)
                if decision_hash is not None:
                    self.repository.save_decision(listing_id, decision_hash, decision)
                if decision_hash is not None:
                    report.decisions.append(
                        EvaluatedListing(
                            listing=listing,
                            content_hash=decision_hash,
                            decision=decision,
                        )
                    )
        return report

    @staticmethod
    def _as_comparable(listing: ListingSnapshot) -> ComparableVehicle:
        assert listing.year is not None
        assert listing.mileage_km is not None
        return ComparableVehicle(
            listing_id=listing.source_listing_id,
            price_aed=listing.price_aed,
            year=listing.year,
            mileage_km=listing.mileage_km,
            seller_type=listing.seller_type,
            observed_at=listing.observed_at,
        )


def money_percent(value: Decimal, percent: Decimal) -> Decimal:
    """Возвращает процент от денежного значения."""
    return (value * percent / Decimal("100")).quantize(Decimal("1"))

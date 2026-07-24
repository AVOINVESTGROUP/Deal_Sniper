"""Оркестрация сбора, истории и детерминированного решения."""

from dataclasses import dataclass, field
from time import perf_counter

from src.config import Settings
from src.domain.comparables import select_comparables
from src.domain.engines import (
    ComparablePriceEngine,
    CostEngine,
    CostPolicy,
    DecisionEngine,
    DecisionPolicy,
    RiskEngine,
)
from src.domain.models import DealDecision, ListingSnapshot
from src.domain.normalization import normalize_listing, resolve_vehicle_identities
from src.raw_storage import (
    GcsRawSnapshotArchive,
    LocalRawSnapshotArchive,
    RawSnapshotArchive,
)
from src.sources.base import CompositeSource, SourceAdapter
from src.sources.cars24 import Cars24Source
from src.sources.carswitch import CarSwitchSource
from src.sources.dubicars import DubiCarsSource
from src.sources.opensooq import OpenSooqSource
from src.storage import LocalRepository, Repository


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
    pending: list[tuple[str, str]] = field(default_factory=list)

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
        repository: Repository,
        sources: dict[str, SourceAdapter],
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.sources = sources
        self.market_engine = ComparablePriceEngine()
        self.risk_engine = RiskEngine()
        self.cost_engine = CostEngine(
            CostPolicy(
                inspection_aed=settings.inspection_cost_aed,
                preparation_aed=settings.preparation_cost_aed,
                base_repair_reserve_aed=settings.base_repair_reserve_aed,
                holding_cost_per_day_aed=settings.holding_cost_per_day_aed,
                expected_hold_days=settings.expected_hold_days,
                annual_capital_percent=settings.annual_capital_percent,
                selling_cost_percent=settings.selling_cost_percent,
                risk_reserve_percent=settings.risk_reserve_percent,
            )
        )
        self.decision_engine = DecisionEngine(
            DecisionPolicy(
                target_profit_aed=settings.target_profit_aed,
                min_roi_percent=settings.min_roi_percent,
                min_comparables=settings.min_comparables_count,
            )
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "DealService":
        archive: RawSnapshotArchive
        if settings.storage_backend == "firestore":
            from src.firestore_storage import FirestoreRepository

            repository: Repository = FirestoreRepository(settings.google_cloud_project)
            archive = GcsRawSnapshotArchive(
                settings.google_cloud_project,
                settings.raw_snapshots_bucket,
                repository,
            )
        else:
            repository = LocalRepository(settings.database_path)
            archive = LocalRawSnapshotArchive(settings.local_raw_snapshots_path, repository)
        sources: dict[str, SourceAdapter] = {
            "dubicars": DubiCarsSource(
                settings.source_url_template,
                pages=settings.source_pages,
                timeout_seconds=settings.request_timeout_seconds,
                archive=archive,
                aed_to_usd_rate=settings.aed_to_usd_rate,
            ),
            "carswitch": CarSwitchSource(
                settings.carswitch_url_template,
                pages=settings.carswitch_pages,
                timeout_seconds=settings.request_timeout_seconds,
                archive=archive,
            ),
            "cars24": Cars24Source(
                settings.cars24_url_template,
                pages=settings.cars24_pages,
                timeout_seconds=settings.request_timeout_seconds,
                archive=archive,
            ),
            "opensooq": OpenSooqSource(
                settings.opensooq_url_template,
                pages=settings.opensooq_pages,
                timeout_seconds=settings.request_timeout_seconds,
                archive=archive,
            ),
        }
        return cls(settings=settings, repository=repository, sources=sources)

    def source_statuses(self) -> dict[str, bool]:
        """Возвращает доступные адаптеры и централизованные переключатели Firestore/SQLite."""
        return {name: self.repository.source_enabled(name, default=True) for name in self.sources}

    def set_source_enabled(self, source_name: str, enabled: bool) -> None:
        """Меняет состояние зарегистрированного адаптера без удаления данных."""
        normalized = source_name.strip().casefold()
        if normalized not in self.sources:
            raise ValueError(f"Неизвестный источник: {source_name}")
        self.repository.set_source_enabled(normalized, enabled)

    async def scan(self, source_name: str | None = None) -> ScanReport:
        """Локальный вертикальный запуск: сбор и обработка изменившихся версий."""
        report = await self.collect(source_name)
        for listing_id, content_hash in report.pending:
            evaluated = await self.process_listing(listing_id, content_hash)
            if evaluated is not None:
                report.decisions.append(evaluated)
        return report

    async def collect(self, source_name: str | None = None) -> ScanReport:
        """Собирает источники и возвращает только новые версии для очереди обработки."""
        if source_name is not None:
            source_key = source_name.strip().casefold()
            if source_key not in self.sources:
                raise ValueError(f"Неизвестный источник: {source_name}")
            source: SourceAdapter = self.sources[source_key]
        else:
            enabled = [
                adapter
                for name, adapter in self.sources.items()
                if self.repository.source_enabled(name, default=True)
            ]
            if not enabled:
                raise RuntimeError("Все источники отключены")
            source = CompositeSource(enabled)
        metric_name = source_name or "composite"
        started = perf_counter()
        try:
            fetched = await source.fetch()
        except Exception as error:
            self.repository.record_source_run(
                metric_name,
                {
                    "success": False,
                    "duration_seconds": round(perf_counter() - started, 3),
                    "error": f"{type(error).__name__}: {error}",
                },
            )
            raise
        report = ScanReport(fetched=len(fetched))
        saved = self.repository.save_snapshots(fetched)
        for listing, is_new, price_changed, content_hash in saved:
            report.new += int(is_new)
            report.changed += int(price_changed)
            listing_id = f"{listing.source}:{listing.source_listing_id}"
            if not self.repository.decision_exists(
                listing_id,
                content_hash,
                self.decision_engine.version,
            ):
                report.pending.append((listing_id, content_hash))

        normalized_fetched = [
            vehicle for listing in fetched if (vehicle := normalize_listing(listing)) is not None
        ]
        if normalized_fetched:
            self.repository.save_normalized_market(normalized_fetched, [])

        self.repository.record_source_run(
            metric_name,
            {
                "success": True,
                "fetched": report.fetched,
                "new": report.new,
                "changed": report.changed,
                "pending": len(report.pending),
                "duration_seconds": round(perf_counter() - started, 3),
            },
        )

        return report

    async def process_listing(
        self,
        listing_id: str,
        content_hash: str,
    ) -> EvaluatedListing | None:
        """Идемпотентно рассчитывает одну версию объявления на актуальном рынке."""
        if self.repository.decision_exists(
            listing_id,
            content_hash,
            self.decision_engine.version,
        ):
            return None

        target_listing = self.repository.latest_snapshot(listing_id)
        target = normalize_listing(target_listing) if target_listing is not None else None
        if target_listing is None or target is None:
            return None
        normalized_vehicles = self.repository.comparable_vehicles(target.make, target.model)
        if all(vehicle.listing_id != target.listing_id for vehicle in normalized_vehicles):
            normalized_vehicles.append(target)
        identities, listing_to_vehicle = resolve_vehicle_identities(normalized_vehicles)
        target_vehicle_id = listing_to_vehicle.get(target.listing_id)
        if target_vehicle_id is not None:
            target_identity = next(
                (identity for identity in identities if identity.vehicle_id == target_vehicle_id),
                None,
            )
            if target_identity is not None:
                self.repository.save_vehicle_identity(target_identity)
        peers = select_comparables(target, normalized_vehicles, listing_to_vehicle)
        market = self.market_engine.estimate(
            peers,
            min_comparables=self.settings.min_comparables_count,
        )
        risks = self.risk_engine.assess(target_listing)
        costs = self.cost_engine.estimate(target_listing.price_aed, risks)
        decision = self.decision_engine.decide(
            asking_price_aed=target_listing.price_aed,
            market=market,
            costs=costs,
            risks=risks,
        )
        self.repository.save_decision(listing_id, content_hash, decision)
        return EvaluatedListing(
            listing=target_listing,
            content_hash=content_hash,
            decision=decision,
        )

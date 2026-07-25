"""Оркестрация сбора, истории и детерминированного решения."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
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
from src.domain.ids import decision_id, verification_key
from src.domain.models import (
    DealDecision,
    FreshnessStatus,
    ListingSnapshot,
    VerificationStatus,
)
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
from src.storage import LocalRepository, Repository, snapshot_hash
from src.verification import (
    EXTRACTOR_VERSION,
    PriceVerification,
    TemporaryVerificationError,
    build_evidence,
    evidence_is_active,
    verify_listing_price,
)

PriceVerifier = Callable[[ListingSnapshot], Awaitable[PriceVerification]]


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
        verifier: PriceVerifier = verify_listing_price,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.sources = sources
        self.verifier = verifier
        self.market_engine = ComparablePriceEngine()
        self.risk_engine = RiskEngine()
        cost_policy = CostPolicy(
            inspection_aed=settings.inspection_cost_aed,
            registration_aed=settings.registration_cost_aed,
            preparation_aed=settings.preparation_cost_aed,
            repair_low_aed=settings.repair_low_aed,
            repair_expected_aed=settings.repair_expected_aed,
            repair_high_aed=settings.repair_high_aed,
            holding_cost_per_day_aed=settings.holding_cost_per_day_aed,
            expected_hold_days=settings.expected_hold_days,
            annual_capital_rate=settings.annual_capital_rate,
            selling_rate=settings.selling_rate,
            risk_rate=settings.risk_rate,
            version=settings.financial_config_version,
        )
        self.cost_engine = CostEngine(cost_policy)
        self.decision_engine = DecisionEngine(
            DecisionPolicy(
                target_profit_aed=settings.target_profit_aed,
                min_roi_percent=settings.min_roi_percent,
                min_comparables=settings.min_comparables_count,
                liquidity_discount_rate=settings.liquidity_discount_rate,
                version=settings.financial_config_version,
            ),
            cost_policy,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "DealService":
        archive: RawSnapshotArchive
        if settings.storage_backend == "firestore":
            from src.firestore_storage import FirestoreRepository

            repository: Repository = FirestoreRepository(
                settings.google_cloud_project, settings.firestore_database
            )
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

        def pending_price(item: tuple[str, str]) -> Decimal:
            snapshot = self.repository.get_snapshot(item[0], item[1])
            return snapshot.price_aed if snapshot is not None else Decimal(0)

        pending = sorted(
            report.pending,
            key=pending_price,
            reverse=True,
        )
        for listing_id, content_hash in pending:
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
            if not self.repository.source_enabled(source_key, default=True):
                raise RuntimeError(f"Источник {source_key} отключён")
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
        affected_make_models: set[tuple[str, str]] = set()
        for listing, is_new, price_changed, _content_hash in saved:
            report.new += int(is_new)
            report.changed += int(price_changed)
            if is_new or price_changed:
                affected_make_models.add(
                    ((listing.make or "").casefold(), (listing.model or "").casefold())
                )
        if affected_make_models:
            report.pending = [
                (
                    f"{listing.source}:{listing.source_listing_id}",
                    snapshot_hash(listing),
                )
                for listing in self.repository.latest_snapshots()
                if ((listing.make or "").casefold(), (listing.model or "").casefold())
                in affected_make_models
            ]
        pending_set = set(report.pending)
        for listing, _is_new, _price_changed, content_hash in saved:
            listing_id = f"{listing.source}:{listing.source_listing_id}"
            key = verification_key(
                listing.source,
                listing_id,
                content_hash,
                EXTRACTOR_VERSION,
            )
            evidence = self.repository.get_verification_evidence(key)
            if evidence is None or not evidence_is_active(evidence):
                pending_set.add((listing_id, content_hash))
        report.pending = sorted(pending_set)

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
        target_listing = self.repository.get_snapshot(listing_id, content_hash)
        is_current = self.repository.is_current_snapshot(listing_id, content_hash)
        if (
            target_listing is None
            or not is_current
            or snapshot_hash(target_listing) != content_hash
        ):
            self.repository.record_audit_event(
                "processing_snapshot_missing_or_mismatched",
                {"listing_id": listing_id, "content_hash": content_hash},
            )
            return None
        key = verification_key(
            target_listing.source,
            listing_id,
            content_hash,
            EXTRACTOR_VERSION,
        )
        previous = self.repository.get_verification_evidence(key)
        if previous is not None and evidence_is_active(previous):
            evidence = previous
        else:
            verification = await self.verifier(target_listing)
            if verification.retriable:
                if previous is None:
                    self.repository.save_verification_evidence(
                        build_evidence(target_listing, content_hash, verification)
                    )
                self.repository.record_audit_event(
                    "verification_temporary_error",
                    {
                        "listing_id": listing_id,
                        "content_hash": content_hash,
                        "reason": verification.reason,
                    },
                )
                raise TemporaryVerificationError(verification.reason)
            evidence = build_evidence(
                target_listing,
                content_hash,
                verification,
                previous=previous,
            )
            self.repository.save_verification_evidence(evidence)
        if not evidence_is_active(evidence) or evidence.verified_price_aed is None:
            self.repository.record_audit_event(
                "processing_verification_rejected",
                {
                    "listing_id": listing_id,
                    "content_hash": content_hash,
                    "status": evidence.status.value,
                    "reason": evidence.rejection_reason,
                },
            )
            return None
        verified_listing = target_listing.model_copy(
            update={"price_aed": evidence.verified_price_aed}
        )
        target = normalize_listing(verified_listing)
        if target is None:
            self.repository.record_audit_event(
                "processing_snapshot_not_normalizable",
                {"listing_id": listing_id, "content_hash": content_hash},
            )
            return None
        target = target.model_copy(
            update={
                "verification_status": evidence.status,
                "evidence_revision_id": evidence.evidence_revision_id,
                "valid_until": evidence.valid_until,
                "freshness_status": evidence.freshness_status,
            }
        )
        self.repository.save_normalized_vehicle(target)
        now = datetime.now(UTC)
        normalized_vehicles = [
            vehicle
            for vehicle in self.repository.comparable_vehicles(target.make, target.model)
            if vehicle.verification_status is VerificationStatus.VERIFIED
            and vehicle.freshness_status is FreshnessStatus.ACTIVE
            and vehicle.valid_until is not None
            and vehicle.valid_until > now
        ]
        if all(vehicle.listing_id != target.listing_id for vehicle in normalized_vehicles):
            normalized_vehicles.append(target)
        identities, listing_to_vehicle = resolve_vehicle_identities(normalized_vehicles)
        target_vehicle_id = listing_to_vehicle.get(target.listing_id)
        if target_vehicle_id is not None:
            target = target.model_copy(update={"vehicle_id": target_vehicle_id})
            self.repository.save_normalized_vehicle(target)
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
        risks = self.risk_engine.assess(verified_listing)
        resale = (
            market.low_aed * (1 - self.settings.liquidity_discount_rate)
            if market is not None
            else verified_listing.price_aed
        )
        costs = self.cost_engine.estimate(verified_listing.price_aed, risks, resale)
        decision = self.decision_engine.decide(
            asking_price_aed=verified_listing.price_aed,
            market=market,
            costs=costs,
            risks=risks,
        )
        fingerprint = (
            market.market_fingerprint
            if market is not None and market.market_fingerprint is not None
            else "insufficient-market"
        )
        stable_decision_id = decision_id(
            listing_id=listing_id,
            content_hash=content_hash,
            engine_version=decision.engine_version,
            financial_config_version=self.settings.financial_config_version,
            verification_version=evidence.evidence_revision_id,
            market_fingerprint_value=fingerprint,
        )
        decision = decision.model_copy(
            update={
                "decision_id": stable_decision_id,
                "decision_subject_id": listing_id,
                "vehicle_id": target.vehicle_id,
                "content_hash": content_hash,
                "financial_config_version": self.settings.financial_config_version,
                "verification_version": evidence.evidence_revision_id,
                "market_fingerprint": fingerprint,
            }
        )
        self.repository.save_decision(listing_id, content_hash, decision)
        return EvaluatedListing(
            listing=verified_listing,
            content_hash=content_hash,
            decision=decision,
        )

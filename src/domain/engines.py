"""Детерминированные движки рыночной цены, затрат, рисков и решения."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from statistics import median

from src.domain.ids import market_fingerprint, money_value
from src.domain.models import (
    MIN_VALID_LISTING_PRICE_AED,
    ComparableVehicle,
    CostEstimate,
    DealDecision,
    DecisionAction,
    ListingSnapshot,
    MarketEstimate,
    RiskAssessment,
)

MONEY_STEP = Decimal("0.01")
INTERMEDIATE_STEP = Decimal("0.0001")
PERCENT_STEP = Decimal("0.1")
DECISION_ENGINE_VERSION = "3.2.0"
FINANCIAL_CONFIG_VERSION = "provisional-2026-07-v1"
ADJUSTMENT_VERSION = "comparable-adjustments/v3"


def money(value: Decimal) -> Decimal:
    """Округляет итоговую денежную сумму до 0.01 AED."""
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def intermediate(value: Decimal) -> Decimal:
    """Сохраняет не менее 0.0001 AED промежуточной точности."""
    return value.quantize(INTERMEDIATE_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """Версионируемые бизнес-пороги решения."""

    target_profit_aed: Decimal = Decimal("5000")
    min_roi_percent: Decimal = Decimal("10")
    min_comparables: int = 5
    liquidity_discount_rate: Decimal = Decimal("0.05")
    version: str = FINANCIAL_CONFIG_VERSION


@dataclass(frozen=True, slots=True)
class CostPolicy:
    """Версионируемые коэффициенты канонической формулы."""

    inspection_aed: Decimal = Decimal("500")
    registration_aed: Decimal = Decimal("800")
    preparation_aed: Decimal = Decimal("1500")
    repair_low_aed: Decimal = Decimal("1000")
    repair_expected_aed: Decimal = Decimal("2500")
    repair_high_aed: Decimal = Decimal("5000")
    holding_cost_per_day_aed: Decimal = Decimal("50")
    expected_hold_days: int = 45
    annual_capital_rate: Decimal = Decimal("0.08")
    selling_rate: Decimal = Decimal("0.02")
    risk_rate: Decimal = Decimal("0.05")
    version: str = FINANCIAL_CONFIG_VERSION

    def __post_init__(self) -> None:
        for name in ("annual_capital_rate", "selling_rate", "risk_rate"):
            value = getattr(self, name)
            if value < 0 or value > 1:
                raise ValueError(f"{name} должен быть долей 0..1")


class RiskEngine:
    """Извлекает проверяемые стоп-факторы до оценки достаточности рынка."""

    STOP_TERMS = (
        "flood",
        "flooded",
        "salvage",
        "chassis damage",
        "chassis damaged",
        "non running",
        "not running",
        "major accident",
        "غرق",
        "غرقان",
        "شاصي متضرر",
        "حادث كبير",
        "لا تعمل",
    )
    WARNING_TERMS = (
        "accident",
        "repaint",
        "repair",
        "imported",
        "warning light",
        "حادث",
        "صبغ",
        "إصلاح",
        "وارد",
    )

    def assess(self, listing: ListingSnapshot) -> RiskAssessment:
        text = f"{listing.title} {listing.description}".casefold()
        stop_flags = [term for term in self.STOP_TERMS if term in text]
        warnings = [term for term in self.WARNING_TERMS if term in text]
        missing = 0
        if not listing.specification:
            warnings.append("Не указана региональная спецификация")
            missing += 1
        if not listing.trim:
            warnings.append("Не указана комплектация")
            missing += 1
        if listing.mileage_km is None:
            warnings.append("Не указан пробег")
            missing += 1
        elif listing.mileage_km > 200_000:
            warnings.append("Пробег выше 200 000 км")
        if listing.year is None:
            missing += 1
        if listing.vin and not _valid_vin(listing.vin):
            warnings.append("VIN не прошёл валидацию")
        quality = max(Decimal("0"), Decimal("1") - Decimal(missing) * Decimal("0.15"))
        return RiskAssessment(
            stop_flags=list(dict.fromkeys(stop_flags)),
            warnings=list(dict.fromkeys(warnings)),
            data_quality_score=quality,
        )


def _valid_vin(value: str) -> bool:
    normalized = value.strip().upper()
    if len(normalized) != 17 or any(character in "IOQ" for character in normalized):
        return False
    if not normalized.isalnum() or len(set(normalized)) < 5:
        return False
    return normalized not in {"0" * 17, "1" * 17, "X" * 17}


class CostEngine:
    """Воспроизводит утверждённую каноническую формулу затрат."""

    def __init__(self, policy: CostPolicy | None = None) -> None:
        self.policy = policy or CostPolicy()

    def estimate(
        self,
        asking_price_aed: Decimal,
        risks: RiskAssessment,
        resale_price_aed: Decimal | None = None,
    ) -> CostEstimate:
        del risks  # предупреждения качества не изображают физический ремонт
        policy = self.policy
        resale = resale_price_aed if resale_price_aed is not None else asking_price_aed
        repair_basis = policy.repair_high_aed
        holding = policy.holding_cost_per_day_aed * Decimal(policy.expected_hold_days)
        capital_rate = (
            policy.annual_capital_rate * Decimal(policy.expected_hold_days) / Decimal("365")
        )
        capital_basis = (
            asking_price_aed
            + policy.inspection_aed
            + policy.registration_aed
            + repair_basis
            + policy.preparation_aed
        )
        capital = capital_basis * capital_rate
        selling = resale * policy.selling_rate
        risk_reserve = (asking_price_aed + repair_basis) * policy.risk_rate
        return CostEstimate(
            inspection_aed=money(policy.inspection_aed),
            registration_aed=money(policy.registration_aed),
            repair_aed=money(repair_basis),
            preparation_aed=money(policy.preparation_aed),
            holding_aed=money(holding),
            capital_aed=money(capital),
            selling_aed=money(selling),
            risk_reserve_aed=money(risk_reserve),
        )


class ComparablePriceEngine:
    """Строит устойчивый независимый рынок без LLM и asking-price target filter."""

    def estimate(
        self, comparables: list[ComparableVehicle], min_comparables: int
    ) -> MarketEstimate | None:
        unique: dict[str, ComparableVehicle] = {}
        for item in comparables:
            key = item.vehicle_id or item.listing_id
            previous = unique.get(key)
            if previous is None or item.observed_at > previous.observed_at:
                unique[key] = item
        if len(unique) < min_comparables:
            return None

        ordered = sorted(
            unique.values(), key=lambda item: item.adjusted_price_aed or item.price_aed
        )
        prices = [item.adjusted_price_aed or item.price_aed for item in ordered]
        center = Decimal(str(median(prices)))
        deviations = [abs(value - center) for value in prices]
        mad = Decimal(str(median(deviations)))
        limit = mad * Decimal("3.5")
        accepted = (
            ordered
            if mad == 0
            else [
                item
                for item in ordered
                if abs((item.adjusted_price_aed or item.price_aed) - center) <= limit
            ]
        )
        rejected = [item for item in ordered if item not in accepted]
        if len(accepted) < min_comparables:
            return None

        # Широкая когорта tier 3 допустима только при ограниченной дисперсии.
        # Это не позволяет получить привлекательный «рынок» из разных поколений
        # или комплектаций одной модели с несопоставимыми ценами.
        if any(item.cohort_tier == 3 for item in accepted):
            accepted_values = [item.adjusted_price_aed or item.price_aed for item in accepted]
            accepted_center = Decimal(str(median(accepted_values)))
            accepted_mad = Decimal(
                str(median(abs(value - accepted_center) for value in accepted_values))
            )
            if accepted_center <= 0 or accepted_mad / accepted_center > Decimal("0.35"):
                return None

        accepted_prices = [item.adjusted_price_aed or item.price_aed for item in accepted]
        count = len(accepted_prices)
        low = accepted_prices[max(0, round((count - 1) * 0.25))]
        high = accepted_prices[min(count - 1, round((count - 1) * 0.75))]
        evidence = [
            {
                "listing_id": item.listing_id,
                "vehicle_id": item.vehicle_id,
                "evidence_revision_id": item.evidence_revision_id,
                "price_aed": money_value(item.price_aed),
                "adjusted_price_aed": money_value(item.adjusted_price_aed or item.price_aed),
                "source_role": item.seller_type.value,
                "cohort_tier": item.cohort_tier,
                "reason": item.reason,
                "accepted": item in accepted,
                "adjustment_version": item.adjustment_version,
            }
            for item in ordered
        ]
        coverage = min(Decimal("1"), Decimal(count) / Decimal(max(min_comparables * 2, 1)))
        return MarketEstimate(
            low_aed=money(low),
            median_aed=money(Decimal(str(median(accepted_prices)))),
            high_aed=money(high),
            comparable_ids=[item.listing_id for item in accepted],
            rejected_ids=[item.listing_id for item in rejected],
            coverage_score=coverage,
            market_fingerprint=market_fingerprint(evidence),
            adjustment_version=ADJUSTMENT_VERSION,
        )


class DecisionEngine:
    """Рассчитывает каноническую прибыль, ROI и максимальную цену покупки."""

    def __init__(
        self,
        policy: DecisionPolicy | None = None,
        cost_policy: CostPolicy | None = None,
    ) -> None:
        self.policy = policy or DecisionPolicy()
        self.cost_policy = cost_policy or CostPolicy()
        self.version = DECISION_ENGINE_VERSION

    def decide(
        self,
        asking_price_aed: Decimal,
        market: MarketEstimate | None,
        costs: CostEstimate,
        risks: RiskAssessment | None = None,
    ) -> DealDecision:
        risk_result = risks or RiskAssessment()
        if risk_result.stop_flags:
            return self._blocked(asking_price_aed, market, costs, risk_result)
        if asking_price_aed < MIN_VALID_LISTING_PRICE_AED:
            return self._insufficient(
                asking_price_aed,
                market,
                costs,
                risk_result,
                "Цена ниже допустимого порога и может быть заглушкой",
            )
        if market is None:
            return self._insufficient(
                asking_price_aed,
                None,
                costs,
                risk_result,
                "Недостаточно сопоставимых объявлений",
            )

        policy = self.policy
        cost_policy = self.cost_policy
        resale = intermediate(market.low_aed * (Decimal("1") - policy.liquidity_discount_rate))
        profit = money(resale - asking_price_aed - costs.total_aed)
        invested = asking_price_aed + costs.total_aed
        roi = (
            (profit / invested * Decimal("100")).quantize(PERCENT_STEP, rounding=ROUND_HALF_UP)
            if invested > 0
            else Decimal("0")
        )

        capital_rate = (
            cost_policy.annual_capital_rate
            * Decimal(cost_policy.expected_hold_days)
            / Decimal("365")
        )
        repair_basis = cost_policy.repair_high_aed
        base_fixed = (
            cost_policy.inspection_aed
            + cost_policy.registration_aed
            + repair_basis
            + cost_policy.preparation_aed
            + cost_policy.holding_cost_per_day_aed * Decimal(cost_policy.expected_hold_days)
        )
        selling = resale * cost_policy.selling_rate
        constant = (
            base_fixed
            + selling
            + capital_rate
            * (
                cost_policy.inspection_aed
                + cost_policy.registration_aed
                + repair_basis
                + cost_policy.preparation_aed
            )
            + cost_policy.risk_rate * repair_basis
        )
        raw_max_purchase = (resale - policy.target_profit_aed - constant) / (
            Decimal("1") + capital_rate + cost_policy.risk_rate
        )
        max_purchase = max(
            Decimal("0"),
            raw_max_purchase.quantize(Decimal("1"), rounding=ROUND_DOWN),
        )

        reasons: list[str] = []
        if max_purchase <= 0:
            action = DecisionAction.REJECT
            reasons.append("Максимальная цена покупки неположительна")
        elif asking_price_aed <= max_purchase and roi >= policy.min_roi_percent:
            if risk_result.warnings:
                action = DecisionAction.INSPECT
                reasons.append("Экономика проходит пороги, но требуется проверка рисков")
            else:
                action = DecisionAction.CONTACT
                reasons.append("Цена не выше максимальной цены покупки")
        elif profit > 0 and roi > 0 and asking_price_aed <= resale:
            action = DecisionAction.WATCH
            reasons.append("Сделка положительная, но не выполнены целевые пороги")
        else:
            action = DecisionAction.REJECT
            reasons.append("Цена не обеспечивает целевую прибыль и ROI")

        confidence = (market.coverage_score * risk_result.data_quality_score).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        reasons.append(f"Полные непокупные расходы: {costs.total_aed:,.2f} AED")
        return DealDecision(
            action=action,
            asking_price_aed=money(asking_price_aed),
            market=market,
            costs=costs,
            risks=risk_result,
            max_purchase_price_aed=max_purchase,
            expected_profit_aed=profit,
            roi_percent=roi,
            confidence=confidence,
            reasons=reasons,
            engine_version=self.version,
            financial_config_version=policy.version,
            market_fingerprint=market.market_fingerprint,
        )

    def _blocked(
        self,
        asking: Decimal,
        market: MarketEstimate | None,
        costs: CostEstimate,
        risks: RiskAssessment,
    ) -> DealDecision:
        return DealDecision(
            action=DecisionAction.REJECT,
            asking_price_aed=money(asking),
            market=market,
            costs=costs,
            risks=risks,
            max_purchase_price_aed=Decimal("0"),
            expected_profit_aed=None,
            roi_percent=None,
            confidence=Decimal("0"),
            reasons=["Обнаружены стоп-факторы"],
            engine_version=self.version,
            financial_config_version=self.policy.version,
        )

    def _insufficient(
        self,
        asking: Decimal,
        market: MarketEstimate | None,
        costs: CostEstimate,
        risks: RiskAssessment,
        reason: str,
    ) -> DealDecision:
        return DealDecision(
            action=DecisionAction.INSUFFICIENT_DATA,
            asking_price_aed=money(asking),
            market=market,
            costs=costs,
            risks=risks,
            max_purchase_price_aed=None,
            expected_profit_aed=None,
            roi_percent=None,
            confidence=Decimal("0"),
            reasons=[reason],
            engine_version=self.version,
            financial_config_version=self.policy.version,
        )

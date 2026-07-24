"""Детерминированные движки рыночной цены и решения."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

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

MONEY_STEP = Decimal("1")
PERCENT_STEP = Decimal("0.1")
DECISION_ENGINE_VERSION = "2.3.0"


def money(value: Decimal) -> Decimal:
    """Округляет денежное значение до целого AED."""
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """Версионируемые бизнес-пороги решения."""

    target_profit_aed: Decimal = Decimal("5000")
    min_roi_percent: Decimal = Decimal("10")
    min_comparables: int = 5
    liquidity_discount_percent: Decimal = Decimal("5")


@dataclass(frozen=True, slots=True)
class CostPolicy:
    """Проверяемые допущения полной непокупной себестоимости."""

    inspection_aed: Decimal = Decimal("500")
    preparation_aed: Decimal = Decimal("1500")
    base_repair_reserve_aed: Decimal = Decimal("2500")
    holding_cost_per_day_aed: Decimal = Decimal("50")
    expected_hold_days: int = 45
    annual_capital_percent: Decimal = Decimal("8")
    selling_cost_percent: Decimal = Decimal("2")
    risk_reserve_percent: Decimal = Decimal("5")


class RiskEngine:
    """Извлекает только объяснимые технические предупреждения из данных объявления."""

    STOP_TERMS = ("flood", "salvage", "non running", "not running", "major accident")
    WARNING_TERMS = ("accident", "repaint", "repair", "imported", "warning light")

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
        quality = max(Decimal("0"), Decimal("1") - Decimal(missing) * Decimal("0.15"))
        return RiskAssessment(
            stop_flags=stop_flags,
            warnings=list(dict.fromkeys(warnings)),
            data_quality_score=quality,
        )


class CostEngine:
    """Рассчитывает инспекцию, ремонт, хранение, капитал, продажу и риск."""

    def __init__(self, policy: CostPolicy | None = None) -> None:
        self.policy = policy or CostPolicy()

    def estimate(
        self,
        asking_price_aed: Decimal,
        risks: RiskAssessment,
    ) -> CostEstimate:
        repair_multiplier = Decimal(len(risks.warnings)) * Decimal("0.25")
        repair = self.policy.base_repair_reserve_aed * (Decimal("1") + repair_multiplier)
        holding = self.policy.holding_cost_per_day_aed * self.policy.expected_hold_days
        capital = (
            asking_price_aed
            * self.policy.annual_capital_percent
            / Decimal("100")
            * Decimal(self.policy.expected_hold_days)
            / Decimal("365")
        )
        selling = asking_price_aed * self.policy.selling_cost_percent / Decimal("100")
        risk_reserve = asking_price_aed * self.policy.risk_reserve_percent / Decimal("100")
        return CostEstimate(
            inspection_aed=money(self.policy.inspection_aed),
            repair_aed=money(repair),
            preparation_aed=money(self.policy.preparation_aed),
            holding_aed=money(holding),
            capital_aed=money(capital),
            selling_aed=money(selling),
            risk_reserve_aed=money(risk_reserve),
        )


class ComparablePriceEngine:
    """Строит устойчивый рыночный диапазон без LLM."""

    def estimate(
        self, comparables: list[ComparableVehicle], min_comparables: int
    ) -> MarketEstimate | None:
        """Удаляет грубые выбросы и возвращает квантили ряда цен."""
        unique = {item.listing_id: item for item in comparables}
        if len(unique) < min_comparables:
            return None

        ordered = sorted(
            unique.values(),
            key=lambda item: item.adjusted_price_aed or item.price_aed,
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

        accepted_prices = [item.adjusted_price_aed or item.price_aed for item in accepted]
        count = len(accepted_prices)
        low = accepted_prices[max(0, round((count - 1) * 0.25))]
        high = accepted_prices[min(count - 1, round((count - 1) * 0.75))]
        coverage = min(Decimal("1"), Decimal(count) / Decimal(max(min_comparables * 2, 1)))
        return MarketEstimate(
            low_aed=money(low),
            median_aed=money(Decimal(str(median(accepted_prices)))),
            high_aed=money(high),
            comparable_ids=[item.listing_id for item in accepted],
            rejected_ids=[item.listing_id for item in rejected],
            coverage_score=coverage,
        )


class DecisionEngine:
    """Рассчитывает максимальную цену покупки, прибыль и действие."""

    def __init__(self, policy: DecisionPolicy | None = None) -> None:
        self.policy = policy or DecisionPolicy()
        self.version = DECISION_ENGINE_VERSION

    def decide(
        self,
        asking_price_aed: Decimal,
        market: MarketEstimate | None,
        costs: CostEstimate,
        risks: RiskAssessment | None = None,
    ) -> DealDecision:
        """Возвращает решение, не используя внешние сервисы."""
        risk_result = risks or RiskAssessment()
        if asking_price_aed < MIN_VALID_LISTING_PRICE_AED:
            return DealDecision(
                action=DecisionAction.INSUFFICIENT_DATA,
                asking_price_aed=asking_price_aed,
                market=market,
                costs=costs,
                risks=risk_result,
                max_purchase_price_aed=None,
                expected_profit_aed=None,
                roi_percent=None,
                confidence=Decimal("0"),
                reasons=["Цена ниже допустимого порога и может быть заглушкой"],
                engine_version=self.version,
            )
        if market is None:
            return DealDecision(
                action=DecisionAction.INSUFFICIENT_DATA,
                asking_price_aed=asking_price_aed,
                market=None,
                costs=costs,
                risks=risk_result,
                max_purchase_price_aed=None,
                expected_profit_aed=None,
                roi_percent=None,
                confidence=Decimal("0"),
                reasons=["Недостаточно сопоставимых объявлений"],
                engine_version=self.version,
            )
        if asking_price_aed < market.low_aed * Decimal("0.5"):
            return DealDecision(
                action=DecisionAction.INSUFFICIENT_DATA,
                asking_price_aed=asking_price_aed,
                market=market,
                costs=costs,
                risks=risk_result,
                max_purchase_price_aed=None,
                expected_profit_aed=None,
                roi_percent=None,
                confidence=Decimal("0"),
                reasons=["Аномальная скидка требует подтверждения цены у источника"],
                engine_version=self.version,
            )

        resale = money(
            market.low_aed
            * (Decimal("1") - self.policy.liquidity_discount_percent / Decimal("100"))
        )
        max_purchase = money(resale - costs.total_aed - self.policy.target_profit_aed)
        profit = money(resale - asking_price_aed - costs.total_aed)
        invested = asking_price_aed + costs.total_aed
        roi = (
            (profit / invested * Decimal("100")).quantize(PERCENT_STEP, rounding=ROUND_HALF_UP)
            if invested > 0
            else Decimal("0")
        )

        reasons: list[str] = []
        if risk_result.stop_flags:
            action = DecisionAction.REJECT
            reasons.append("Обнаружены стоп-факторы")
        elif asking_price_aed <= max_purchase and roi >= self.policy.min_roi_percent:
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
        reasons.append(f"Полные непокупные расходы: {costs.total_aed:,.0f} AED")
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
        )

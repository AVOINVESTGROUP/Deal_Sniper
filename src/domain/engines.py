"""Детерминированные движки рыночной цены и решения."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from src.domain.models import (
    ComparableVehicle,
    CostEstimate,
    DealDecision,
    DecisionAction,
    MarketEstimate,
    RiskAssessment,
)

MONEY_STEP = Decimal("1")
PERCENT_STEP = Decimal("0.1")


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


class ComparablePriceEngine:
    """Строит устойчивый рыночный диапазон без LLM."""

    def estimate(
        self, comparables: list[ComparableVehicle], min_comparables: int
    ) -> MarketEstimate | None:
        """Удаляет грубые выбросы и возвращает квантили ряда цен."""
        unique = {item.listing_id: item for item in comparables}
        if len(unique) < min_comparables:
            return None

        ordered = sorted(unique.values(), key=lambda item: item.price_aed)
        prices = [item.price_aed for item in ordered]
        center = Decimal(str(median(prices)))
        deviations = [abs(value - center) for value in prices]
        mad = Decimal(str(median(deviations)))
        limit = mad * Decimal("3.5")
        accepted = (
            ordered
            if mad == 0
            else [item for item in ordered if abs(item.price_aed - center) <= limit]
        )
        rejected = [item for item in ordered if item not in accepted]

        if len(accepted) < min_comparables:
            return None

        accepted_prices = [item.price_aed for item in accepted]
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

    def decide(
        self,
        asking_price_aed: Decimal,
        market: MarketEstimate | None,
        costs: CostEstimate,
        risks: RiskAssessment | None = None,
    ) -> DealDecision:
        """Возвращает решение, не используя внешние сервисы."""
        risk_result = risks or RiskAssessment()
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
            action = DecisionAction.CONTACT
            reasons.append("Цена не выше максимальной цены покупки")
        elif asking_price_aed <= resale and not risk_result.warnings:
            action = DecisionAction.WATCH
            reasons.append("Есть запас до цены перепродажи, но не выполнены целевые пороги")
        elif risk_result.warnings:
            action = DecisionAction.INSPECT
            reasons.append("Перед решением требуется проверка предупреждений")
        else:
            action = DecisionAction.REJECT
            reasons.append("Цена не обеспечивает целевую прибыль и ROI")

        return DealDecision(
            action=action,
            asking_price_aed=money(asking_price_aed),
            market=market,
            costs=costs,
            risks=risk_result,
            max_purchase_price_aed=max_purchase,
            expected_profit_aed=profit,
            roi_percent=roi,
            confidence=market.coverage_score,
            reasons=reasons,
        )

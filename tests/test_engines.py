"""Проверки детерминированного расчётного ядра."""

from datetime import UTC, datetime
from decimal import Decimal

from src.domain.engines import ComparablePriceEngine, DecisionEngine, DecisionPolicy
from src.domain.models import ComparableVehicle, CostEstimate, DecisionAction, SellerType


def comparable(index: int, price: str) -> ComparableVehicle:
    """Создаёт тестовый аналог."""
    return ComparableVehicle(
        listing_id=f"car-{index}",
        price_aed=Decimal(price),
        year=2022,
        mileage_km=50_000,
        seller_type=SellerType.PRIVATE,
        observed_at=datetime.now(UTC),
    )


def test_market_requires_minimum_comparables() -> None:
    engine = ComparablePriceEngine()
    assert engine.estimate([comparable(1, "50000")], min_comparables=3) is None


def test_market_rejects_large_outlier() -> None:
    engine = ComparablePriceEngine()
    items = [
        comparable(1, "50000"),
        comparable(2, "51000"),
        comparable(3, "52000"),
        comparable(4, "53000"),
        comparable(5, "500000"),
    ]
    result = engine.estimate(items, min_comparables=4)
    assert result is not None
    assert result.median_aed == Decimal("51500")
    assert result.rejected_ids == ["car-5"]


def test_profitable_listing_returns_contact() -> None:
    market = ComparablePriceEngine().estimate(
        [comparable(index, str(100000 + index * 1000)) for index in range(6)],
        min_comparables=5,
    )
    decision = DecisionEngine(
        DecisionPolicy(target_profit_aed=Decimal("5000"), min_roi_percent=Decimal("10"))
    ).decide(
        asking_price_aed=Decimal("70000"),
        market=market,
        costs=CostEstimate(repair_aed=Decimal("5000"), risk_reserve_aed=Decimal("2000")),
    )
    assert decision.action is DecisionAction.CONTACT
    assert decision.expected_profit_aed is not None
    assert decision.expected_profit_aed > Decimal("0")


def test_missing_market_never_invents_price() -> None:
    decision = DecisionEngine().decide(
        asking_price_aed=Decimal("70000"),
        market=None,
        costs=CostEstimate(),
    )
    assert decision.action is DecisionAction.INSUFFICIENT_DATA
    assert decision.max_purchase_price_aed is None

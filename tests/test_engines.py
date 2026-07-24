"""Проверки детерминированного расчётного ядра."""

from datetime import UTC, datetime
from decimal import Decimal

from src.bot import format_card, telegram_language
from src.domain.engines import (
    ComparablePriceEngine,
    CostEngine,
    CostPolicy,
    DecisionEngine,
    DecisionPolicy,
    RiskEngine,
)
from src.domain.models import (
    ComparableVehicle,
    CostEstimate,
    DecisionAction,
    ListingSnapshot,
    RiskAssessment,
    SellerType,
)


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


def test_cost_and_risk_engines_cover_full_cost_structure() -> None:
    listing = ListingSnapshot(
        source="test",
        source_listing_id="risk-1",
        url="https://example.com/risk-1",
        title="Toyota Camry repaired after accident",
        price_aed=Decimal("80000"),
        make="Toyota",
        model="Camry",
        year=2022,
        mileage_km=80_000,
    )
    risks = RiskEngine().assess(listing)
    costs = CostEngine(CostPolicy()).estimate(listing.price_aed, risks)
    assert risks.warnings
    assert risks.data_quality_score < Decimal("1")
    assert costs.inspection_aed > 0
    assert costs.repair_aed > 0
    assert costs.holding_aed > 0
    assert costs.capital_aed > 0
    assert costs.selling_aed > 0
    assert costs.risk_reserve_aed > 0


def test_warning_never_promotes_unprofitable_listing_to_inspect() -> None:
    market = ComparablePriceEngine().estimate(
        [comparable(index, str(135000 + index * 500)) for index in range(6)],
        min_comparables=5,
    )
    decision = DecisionEngine().decide(
        asking_price_aed=Decimal("145097"),
        market=market,
        costs=CostEstimate(repair_aed=Decimal("15000")),
        risks=RiskAssessment(warnings=["Требуется проверка"]),
    )
    assert decision.expected_profit_aed is not None
    assert decision.expected_profit_aed < 0
    assert decision.action is DecisionAction.REJECT


def test_warning_returns_inspect_only_for_profitable_listing() -> None:
    market = ComparablePriceEngine().estimate(
        [comparable(index, str(110000 + index * 1000)) for index in range(6)],
        min_comparables=5,
    )
    decision = DecisionEngine().decide(
        asking_price_aed=Decimal("70000"),
        market=market,
        costs=CostEstimate(repair_aed=Decimal("3000")),
        risks=RiskAssessment(warnings=["Требуется проверка"]),
    )
    assert decision.expected_profit_aed is not None
    assert decision.expected_profit_aed > 0
    assert decision.action is DecisionAction.INSPECT


def test_telegram_card_uses_channel_english_and_device_russian() -> None:
    listing = ListingSnapshot(
        source="test",
        source_listing_id="localized-1",
        url="https://example.com/localized-1",
        title="Toyota Camry",
        price_aed=Decimal("70000"),
    )
    decision = DecisionEngine().decide(
        asking_price_aed=listing.price_aed,
        market=None,
        costs=CostEstimate(),
    )

    assert "Price:" in format_card(listing, decision, language="en")
    assert "Expected profit:" in format_card(listing, decision, language="en")
    assert "Цена:" in format_card(listing, decision, language="ru")
    assert telegram_language("ru-RU") == "ru"
    assert telegram_language("ar") == "en"

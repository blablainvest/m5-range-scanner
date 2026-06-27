import pytest

from backend.app.models import Candle
from backend.app.trade_plan import build_trade_plan, build_trade_plan_variants


def candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=index * 300_000,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=100,
        turnover=10_000,
    )


def test_long_plan_uses_lower_wicks_of_recent_shelf_and_targets_3r() -> None:
    candles = [
        candle(0, high=100.2, low=99.2, close=99.6),
        candle(1, high=100.9, low=100.1, close=100.7),
        candle(2, high=101.0, low=100.2, close=100.8),
        candle(3, high=100.95, low=100.3, close=100.75),
    ]

    plan = build_trade_plan(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=100.8,
        tick_size=0.01,
        range_candles=candles,
    )

    assert plan.status == "READY"
    assert plan.entry_price == 101
    assert plan.stop_loss == 100.08
    assert plan.risk_price == pytest.approx(0.92)
    assert plan.take_profit == 103.76
    assert plan.reward_risk == 3
    assert plan.shelf_start_timestamp == 300_000


def test_short_plan_uses_upper_wicks_and_tick_rounding() -> None:
    candles = [
        candle(0, high=99.5, low=99.1, close=99.4),
        candle(1, high=99.4, low=99.05, close=99.3),
        candle(2, high=99.35, low=99.0, close=99.2),
    ]

    plan = build_trade_plan(
        direction="SHORT",
        support=99,
        resistance=101,
        current_price=99.2,
        tick_size=0.05,
        range_candles=candles,
    )

    assert plan.status == "READY"
    assert plan.entry_price == 99
    assert plan.stop_loss == 99.6
    assert plan.take_profit == 97.2


def test_plan_rejects_missing_shelf_and_deep_stop() -> None:
    no_shelf = [
        candle(0, high=100.5, low=99.5, close=100),
        candle(1, high=100.6, low=99.6, close=100.1),
        candle(2, high=100.7, low=99.7, close=100.2),
    ]
    deep_shelf = [
        candle(0, high=101, low=99.8, close=100.8),
        candle(1, high=101, low=99.7, close=100.9),
        candle(2, high=101, low=99.6, close=100.8),
    ]

    missing = build_trade_plan(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=100,
        tick_size=0.01,
        range_candles=no_shelf,
    )
    deep = build_trade_plan(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=100.8,
        tick_size=0.01,
        range_candles=deep_shelf,
    )

    assert missing.status == "INVALID"
    assert deep.status == "INVALID"
    assert "50%" in (deep.reason or "")


def test_neutral_and_already_crossed_entries_do_not_create_plan() -> None:
    shelf = [
        candle(0, high=101, low=100.4, close=100.8),
        candle(1, high=101, low=100.5, close=100.9),
        candle(2, high=101, low=100.6, close=100.9),
    ]

    neutral = build_trade_plan(
        direction="NEUTRAL",
        support=99,
        resistance=101,
        current_price=100,
        tick_size=0.01,
        range_candles=shelf,
    )
    crossed = build_trade_plan(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=101.1,
        tick_size=0.01,
        range_candles=shelf,
    )

    assert neutral.status == "NOT_APPLICABLE"
    assert crossed.status == "INVALID"


def test_v2_enters_after_buffer_but_uses_shelf_stop() -> None:
    shelf = [
        candle(0, high=100.9, low=100.2, close=100.8),
        candle(1, high=101.0, low=100.3, close=100.9),
        candle(2, high=101.0, low=100.4, close=100.85),
    ]

    plans = build_trade_plan_variants(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=100.8,
        tick_size=0.01,
        range_candles=shelf,
        context_candles=shelf,
    )
    v2 = next(plan for plan in plans if plan.version == "breakout-buffer-v2")

    assert v2.status == "READY"
    assert v2.activation == "price_crosses_buffer"
    assert v2.entry_price > 101
    assert v2.stop_loss == 100.18
    assert v2.risk_price == pytest.approx(v2.entry_price - 100.18)
    assert v2.target_3r == pytest.approx(v2.entry_price + v2.risk_price * 3)


def test_v2_rejects_shelf_stop_deeper_than_half_range() -> None:
    deep_shelf = [
        candle(0, high=101.0, low=99.8, close=100.8),
        candle(1, high=101.0, low=99.7, close=100.9),
        candle(2, high=101.0, low=99.6, close=100.85),
    ]

    plans = build_trade_plan_variants(
        direction="LONG",
        support=99,
        resistance=101,
        current_price=100.8,
        tick_size=0.01,
        range_candles=deep_shelf,
        context_candles=deep_shelf,
    )
    v2 = next(plan for plan in plans if plan.version == "breakout-buffer-v2")

    assert v2.status == "INVALID"
    assert v2.reason == "stop is deeper than 50% of range"

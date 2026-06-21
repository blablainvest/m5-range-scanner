from datetime import datetime, timezone

import pytest

from backend.app.database import TradePlanVariant
from backend.app.ml_pipeline import evaluate_breakout, evaluate_plan
from backend.app.models import Candle


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


def test_breakout_labels_distinguish_wick_close_confirmed_and_false_breakout() -> None:
    evaluation = evaluate_breakout(
        support=99,
        resistance=101,
        buffer_price=0.1,
        candles=[
            candle(0, high=101.2, low=100, close=100.8),
            candle(1, high=101.4, low=100.8, close=101.2),
            candle(2, high=101.5, low=101, close=101.3),
            candle(3, high=101.2, low=99.8, close=100.7),
        ],
    )

    assert evaluation.wick_breakout is True
    assert evaluation.close_breakout is True
    assert evaluation.confirmed_breakout is True
    assert evaluation.false_breakout is True
    assert evaluation.breakout_direction == "LONG"
    assert evaluation.first_breakout_at == datetime.fromtimestamp(300, tz=timezone.utc)


def test_confirmed_retest_plan_does_not_enter_without_retest() -> None:
    plan = TradePlanVariant(
        snapshot_id=1,
        plan_version="confirmed-retest-v3",
        status="CONDITIONAL",
        direction="LONG",
        activation="two_m5_closes_then_retest",
        entry_price=101,
        stop_loss=100,
        risk_price=1,
        target_1r=102,
        target_2r=103,
        target_3r=104,
        trigger_price=101.1,
        retest_zone_low=100.9,
        retest_zone_high=101.1,
        parameters_json={},
    )
    m5 = [
        candle(0, high=101.5, low=101.2, close=101.3),
        candle(1, high=101.7, low=101.2, close=101.4),
        candle(2, high=102, low=101.2, close=101.8),
    ]
    m1 = [
        Candle(
            timestamp=index * 60_000,
            open=101.4,
            high=102,
            low=101.2,
            close=101.5,
            volume=100,
            turnover=10_000,
        )
        for index in range(15)
    ]

    evaluation = evaluate_plan(plan, m1, m5)

    assert evaluation.outcome == "NO_TRADE"
    assert evaluation.entered_at is None


def test_confirmed_retest_uses_retest_extreme_for_actual_stop_and_targets() -> None:
    plan = TradePlanVariant(
        snapshot_id=1,
        plan_version="confirmed-retest-v3",
        status="CONDITIONAL",
        direction="LONG",
        activation="two_m5_closes_then_retest",
        entry_price=101,
        stop_loss=100,
        risk_price=1,
        target_1r=102,
        target_2r=103,
        target_3r=104,
        trigger_price=101.1,
        retest_zone_low=100.9,
        retest_zone_high=101.1,
        parameters_json={},
    )
    m5 = [
        candle(0, high=101.5, low=101.2, close=101.3),
        candle(1, high=101.7, low=101.2, close=101.4),
        candle(2, high=101.4, low=100.95, close=101.2),
    ]
    m1 = [
        Candle(
            timestamp=600_000,
            open=101,
            high=101.4,
            low=100.94,
            close=101.2,
            volume=100,
            turnover=10_000,
        )
    ]

    evaluation = evaluate_plan(plan, m1, m5)

    assert evaluation.entered_at == datetime.fromtimestamp(600, tz=timezone.utc)
    assert evaluation.stop_loss == pytest.approx(100.85)
    assert evaluation.target_1r == pytest.approx(101.15)


def test_entered_plan_without_1r_stays_pending() -> None:
    plan = TradePlanVariant(
        snapshot_id=1,
        plan_version="wick-shelf-v1",
        status="READY",
        direction="LONG",
        activation="boundary_touch",
        entry_price=101,
        stop_loss=100,
        risk_price=1,
        target_1r=102,
        target_2r=103,
        target_3r=104,
        parameters_json={},
    )
    m1 = [
        Candle(
            timestamp=0,
            open=101,
            high=101.4,
            low=100.6,
            close=101.2,
            volume=100,
            turnover=10_000,
        )
    ]

    evaluation = evaluate_plan(plan, m1, [])

    assert evaluation.outcome == "PENDING"
    assert evaluation.entered_at == datetime.fromtimestamp(0, tz=timezone.utc)

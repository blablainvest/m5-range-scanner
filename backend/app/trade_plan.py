from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Optional

from .models import Candle, TradePlanView


TRADE_PLAN_VERSION = "wick-shelf-v1"


@dataclass(frozen=True)
class TradePlan:
    status: str
    reason: Optional[str] = None
    version: str = TRADE_PLAN_VERSION
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_price: Optional[float] = None
    reward_risk: Optional[float] = None
    shelf_start_timestamp: Optional[int] = None
    shelf_end_timestamp: Optional[int] = None


def _round_to_tick(value: float, tick_size: float, rounding: str) -> float:
    tick = Decimal(str(tick_size))
    units = Decimal(str(value)) / tick
    mode = ROUND_FLOOR if rounding == "down" else ROUND_CEILING
    return float(units.to_integral_value(rounding=mode) * tick)


def _shelf_candles(
    candles: list[Candle],
    direction: str,
    support: float,
    resistance: float,
) -> list[Candle]:
    width = resistance - support
    if width <= 0:
        return []
    selected: list[Candle] = []
    for candle in reversed(candles[-7:]):
        near_boundary = (
            candle.close >= resistance - width * 0.25
            if direction == "LONG"
            else candle.close <= support + width * 0.25
        )
        if not near_boundary:
            break
        selected.append(candle)
    selected.reverse()
    return selected if len(selected) >= 3 else []


def build_trade_plan(
    *,
    direction: str,
    support: float,
    resistance: float,
    current_price: float,
    tick_size: float,
    range_candles: list[Candle],
) -> TradePlan:
    if direction not in {"LONG", "SHORT"}:
        return TradePlan(status="NOT_APPLICABLE", reason="direction is neutral")
    if resistance <= support:
        return TradePlan(status="INVALID", reason="invalid range boundaries")

    entry = resistance if direction == "LONG" else support
    if (direction == "LONG" and current_price > entry) or (direction == "SHORT" and current_price < entry):
        return TradePlan(status="INVALID", reason="price already crossed entry")

    shelf = _shelf_candles(range_candles, direction, support, resistance)
    if not shelf:
        return TradePlan(status="INVALID", reason="no 3-7 candle shelf near entry")

    buffer_price = tick_size * 2
    if direction == "LONG":
        stop = _round_to_tick(min(candle.low for candle in shelf) - buffer_price, tick_size, "down")
        entry = _round_to_tick(entry, tick_size, "up")
        risk = entry - stop
    else:
        stop = _round_to_tick(max(candle.high for candle in shelf) + buffer_price, tick_size, "up")
        entry = _round_to_tick(entry, tick_size, "down")
        risk = stop - entry

    width = resistance - support
    if risk <= 0:
        return TradePlan(status="INVALID", reason="stop is on the wrong side of entry")
    if risk > width * 0.5:
        return TradePlan(status="INVALID", reason="stop is deeper than 50% of range")
    if stop <= support or stop >= resistance:
        return TradePlan(status="INVALID", reason="stop is outside the range")

    if direction == "LONG":
        target = _round_to_tick(entry + risk * 3, tick_size, "up")
    else:
        target = _round_to_tick(entry - risk * 3, tick_size, "down")

    return TradePlan(
        status="READY",
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        risk_price=risk,
        reward_risk=3.0,
        shelf_start_timestamp=shelf[0].timestamp,
        shelf_end_timestamp=shelf[-1].timestamp,
    )


def atr_14(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    true_ranges: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    values = true_ranges[-14:]
    return sum(values) / len(values) if values else 0.0


def breakout_buffer(tick_size: float, atr_value: float) -> float:
    return max(tick_size * 2, atr_value * 0.1)


def _targets(direction: str, entry: float, risk: float, tick_size: float) -> tuple[float, float, float]:
    if direction == "LONG":
        return (
            _round_to_tick(entry + risk, tick_size, "up"),
            _round_to_tick(entry + risk * 2, tick_size, "up"),
            _round_to_tick(entry + risk * 3, tick_size, "up"),
        )
    return (
        _round_to_tick(entry - risk, tick_size, "down"),
        _round_to_tick(entry - risk * 2, tick_size, "down"),
        _round_to_tick(entry - risk * 3, tick_size, "down"),
    )


def _view_from_v1(
    plan: TradePlan,
    *,
    direction: str,
    support: float,
    resistance: float,
) -> TradePlanView:
    suggested_entry = resistance if direction == "LONG" else support
    entry = plan.entry_price if plan.entry_price is not None else suggested_entry
    target_1r = target_2r = target_3r = None
    if plan.risk_price is not None and plan.risk_price > 0:
        if direction == "LONG":
            target_1r = entry + plan.risk_price
            target_2r = entry + plan.risk_price * 2
        else:
            target_1r = entry - plan.risk_price
            target_2r = entry - plan.risk_price * 2
        target_3r = plan.take_profit
    return TradePlanView(
        version=TRADE_PLAN_VERSION,
        status=plan.status,
        reason=plan.reason,
        direction=direction,
        activation="boundary_touch",
        entry_price=entry,
        stop_loss=plan.stop_loss,
        risk_price=plan.risk_price,
        target_1r=target_1r,
        target_2r=target_2r,
        target_3r=target_3r,
        trigger_price=entry,
    )


def build_trade_plan_variants(
    *,
    direction: str,
    support: float,
    resistance: float,
    current_price: float,
    tick_size: float,
    range_candles: list[Candle],
    context_candles: Optional[list[Candle]] = None,
) -> list[TradePlanView]:
    v1 = build_trade_plan(
        direction=direction,
        support=support,
        resistance=resistance,
        current_price=current_price,
        tick_size=tick_size,
        range_candles=range_candles,
    )
    views = [_view_from_v1(v1, direction=direction, support=support, resistance=resistance)]
    width = resistance - support
    atr_value = atr_14(context_candles or range_candles)
    buffer_price = breakout_buffer(tick_size, atr_value)
    if direction not in {"LONG", "SHORT"} or width <= 0:
        return views

    if direction == "LONG":
        v2_entry = _round_to_tick(resistance + buffer_price, tick_size, "up")
        shelf = _shelf_candles(range_candles, direction, support, resistance)
        v2_stop = (
            _round_to_tick(min(candle.low for candle in shelf) - tick_size * 2, tick_size, "down")
            if shelf
            else None
        )
        v2_risk = v2_entry - v2_stop if v2_stop is not None else None
        stop_depth = resistance - v2_stop if v2_stop is not None else None
    else:
        v2_entry = _round_to_tick(support - buffer_price, tick_size, "down")
        shelf = _shelf_candles(range_candles, direction, support, resistance)
        v2_stop = (
            _round_to_tick(max(candle.high for candle in shelf) + tick_size * 2, tick_size, "up")
            if shelf
            else None
        )
        v2_risk = v2_stop - v2_entry if v2_stop is not None else None
        stop_depth = v2_stop - support if v2_stop is not None else None

    v2_reason = None
    if not shelf:
        v2_reason = "no 3-7 candle shelf near entry"
    elif v2_stop is None or v2_risk is None or v2_risk <= 0:
        v2_reason = "stop is on the wrong side of entry"
    elif stop_depth is None or stop_depth > width * 0.5:
        v2_reason = "stop is deeper than 50% of range"
    elif v2_stop <= support or v2_stop >= resistance:
        v2_reason = "stop is outside the range"
    v2_status = "READY" if v2_reason is None else "INVALID"
    v2_targets = _targets(direction, v2_entry, v2_risk or 0.0, tick_size) if v2_status == "READY" else (None, None, None)
    views.append(
        TradePlanView(
            version="breakout-buffer-v2",
            status=v2_status,
            reason=v2_reason,
            direction=direction,
            activation="price_crosses_buffer",
            entry_price=v2_entry,
            stop_loss=v2_stop if v2_status == "READY" else None,
            risk_price=v2_risk if v2_status == "READY" else None,
            target_1r=v2_targets[0],
            target_2r=v2_targets[1],
            target_3r=v2_targets[2],
            trigger_price=v2_entry,
        )
    )

    retest_half_width = max(buffer_price, tick_size * 2)
    if direction == "LONG":
        v3_trigger = _round_to_tick(resistance + buffer_price, tick_size, "up")
        v3_entry = _round_to_tick(resistance, tick_size, "up")
        v3_stop = _round_to_tick(max(support + width * 0.5, resistance - max(atr_value, width * 0.2)), tick_size, "down")
        retest_low = _round_to_tick(resistance - retest_half_width, tick_size, "down")
        retest_high = _round_to_tick(resistance + retest_half_width, tick_size, "up")
        v3_risk = v3_entry - v3_stop
    else:
        v3_trigger = _round_to_tick(support - buffer_price, tick_size, "down")
        v3_entry = _round_to_tick(support, tick_size, "down")
        v3_stop = _round_to_tick(min(resistance - width * 0.5, support + max(atr_value, width * 0.2)), tick_size, "up")
        retest_low = _round_to_tick(support - retest_half_width, tick_size, "down")
        retest_high = _round_to_tick(support + retest_half_width, tick_size, "up")
        v3_risk = v3_stop - v3_entry
    v3_status = "CONDITIONAL" if v3_risk > 0 and v3_risk <= width * 0.75 else "INVALID"
    v3_reason = "awaiting two closes and retest" if v3_status == "CONDITIONAL" else "retest stop is too deep"
    v3_targets = _targets(direction, v3_entry, v3_risk, tick_size) if v3_status == "CONDITIONAL" else (None, None, None)
    views.append(
        TradePlanView(
            version="confirmed-retest-v3",
            status=v3_status,
            reason=v3_reason,
            direction=direction,
            activation="two_m5_closes_then_retest",
            entry_price=v3_entry,
            stop_loss=v3_stop if v3_status == "CONDITIONAL" else None,
            risk_price=v3_risk if v3_status == "CONDITIONAL" else None,
            target_1r=v3_targets[0],
            target_2r=v3_targets[1],
            target_3r=v3_targets[2],
            trigger_price=v3_trigger,
            retest_zone_low=retest_low,
            retest_zone_high=retest_high,
        )
    )
    return views

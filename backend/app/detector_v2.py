from __future__ import annotations

import math
from statistics import mean
from typing import Optional

from .analysis import (
    btc_context,
    closed_candles,
    count_false_breakouts,
    count_independent_zone_touches,
    direction_from_trend,
    previous_trend,
    price_position,
    setup_class,
    to_chart_candles,
)
from .models import Candle, ScanResult, Ticker
from .trade_plan import atr_14, build_trade_plan_variants


DETECTOR_VERSION = "range-episode-v2"
CANONICAL_TRADE_PLAN_VERSION = "breakout-buffer-v2"
WINDOWS = (12, 18, 24, 36, 48, 60)


def _quantile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[position]


def _boundaries(candles: list[Candle]) -> tuple[float, float]:
    return _quantile([c.low for c in candles], 0.15), _quantile([c.high for c in candles], 0.85)


def _inside_ratios(candles: list[Candle], support: float, resistance: float) -> tuple[float, float]:
    if not candles:
        return 0.0, 0.0
    close_inside = sum(support <= c.close <= resistance for c in candles) / len(candles)
    body_inside = sum(
        min(c.open, c.close) >= support and max(c.open, c.close) <= resistance
        for c in candles
    ) / len(candles)
    return close_inside, body_inside


def _regression_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values))) or 1
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    return slope / y_mean if y_mean else 0.0


def _expand_range(closed: list[Candle], start: int, support: float, resistance: float) -> int:
    width = resistance - support
    while start >= 5 and width > 0:
        candidate_start = start - 5
        candidate = closed[candidate_start:]
        candidate_support, candidate_resistance = _boundaries(candidate)
        close_inside, body_inside = _inside_ratios(candidate, support, resistance)
        boundary_shift = max(
            abs(candidate_support - support),
            abs(candidate_resistance - resistance),
        ) / width
        if close_inside < 0.80 or body_inside < 0.65 or boundary_shift > 0.15:
            break
        start = candidate_start
    return start


def _score(
    *,
    candles: list[Candle],
    prior: list[Candle],
    support: float,
    resistance: float,
    direction: str,
    position: float,
    ticker: Ticker,
) -> tuple[int, dict[str, float]]:
    width = resistance - support
    close_inside, body_inside = _inside_ratios(candles, support, resistance)
    first_half, second_half = candles[: max(1, len(candles) // 2)], candles[max(1, len(candles) // 2) :]
    first_span = max(c.high for c in first_half) - min(c.low for c in first_half)
    second_span = max(c.high for c in second_half) - min(c.low for c in second_half)
    contraction = max(0.0, min(1.0, 1 - second_span / first_span)) if first_span > 0 else 0.0
    support_touches = count_independent_zone_touches(candles, support, resistance, "support")
    resistance_touches = count_independent_zone_touches(candles, support, resistance, "resistance")
    touches = min(1.0, min(support_touches, resistance_touches) / 3)
    pressure = position if direction == "LONG" else 1 - position
    age = min(1.0, len(candles) / 60)
    turnover_now = mean(c.turnover for c in candles[-6:])
    turnover_before = mean(c.turnover for c in prior[-12:]) if prior else turnover_now
    volume_ratio = turnover_now / turnover_before if turnover_before else 1.0
    volume_score = min(1.0, volume_ratio / 1.5)
    trend_closes = [c.close for c in prior[-50:]]
    trend_return = (
        abs(trend_closes[-1] / trend_closes[0] - 1)
        if len(trend_closes) >= 2 and trend_closes[0] > 0
        else 0.0
    )
    impulse = min(1.0, trend_return / max(width / support if support > 0 else 0.01, 0.005))
    stability = max(0.0, min(1.0, close_inside * 0.6 + body_inside * 0.4))
    score = round(
        stability * 25
        + touches * 15
        + contraction * 15
        + pressure * 15
        + age * 10
        + volume_score * 10
        + impulse * 10
    )
    metrics = {
        "boundary_stability": stability,
        "volatility_contraction": contraction,
        "pressure_score": pressure,
        "age_score": age,
        "volume_score": volume_score,
        "preceding_impulse": impulse,
        "close_inside_ratio": close_inside,
        "body_inside_ratio": body_inside,
        "volume_ratio": volume_ratio,
        "support_touches": float(support_touches),
        "resistance_touches": float(resistance_touches),
        "range_slope": _regression_slope([c.close for c in candles]),
    }
    return min(100, max(0, score)), metrics


def detect_v2(
    ticker: Ticker,
    candles: list[Candle],
    tick_size: float,
    now_ms: int,
    btc_candles: Optional[list[Candle]] = None,
) -> Optional[ScanResult]:
    closed = closed_candles(candles, now_ms)
    if len(closed) < max(WINDOWS) + 30:
        return None

    best: Optional[tuple[int, int, float, float, str, str, str, dict[str, float]]] = None
    for window in WINDOWS:
        start = len(closed) - window
        seed = closed[start:]
        support, resistance = _boundaries(seed)
        if support <= 0 or resistance <= support:
            continue
        width_pct = (resistance - support) / support * 100
        if width_pct < 0.1 or width_pct > 3.0:
            continue
        start = _expand_range(closed, start, support, resistance)
        range_candles = closed[start:]
        support, resistance = _boundaries(range_candles)
        prior = closed[max(0, start - 50) : start]
        trend = previous_trend(prior)
        position = price_position(ticker.last_price, support, resistance)
        direction, status, alignment = direction_from_trend(position, trend)
        score, metrics = _score(
            candles=range_candles,
            prior=prior,
            support=support,
            resistance=resistance,
            direction=direction,
            position=position,
            ticker=ticker,
        )
        candidate = (score, start, support, resistance, direction, status, alignment, metrics)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        return None

    score, start, support, resistance, direction, status, alignment, metrics = best
    range_candles = closed[start:]
    prior = closed[max(0, start - 50) : start]
    trend = previous_trend(prior)
    position = price_position(ticker.last_price, support, resistance)
    atr_value = atr_14(closed[max(0, len(closed) - 31) :])
    plans = build_trade_plan_variants(
        direction=direction,
        support=support,
        resistance=resistance,
        current_price=ticker.last_price,
        tick_size=tick_size,
        range_candles=range_candles,
        context_candles=prior + range_candles,
    )
    canonical_plan = next(
        (plan for plan in plans if plan.version == CANONICAL_TRADE_PLAN_VERSION),
        plans[0] if plans else None,
    )
    reward_risk = (
        abs(canonical_plan.target_3r - canonical_plan.entry_price) / canonical_plan.risk_price
        if canonical_plan is not None
        and canonical_plan.entry_price is not None
        and canonical_plan.target_3r is not None
        and canonical_plan.risk_price
        and canonical_plan.risk_price > 0
        else None
    )
    btc = btc_context(ticker.symbol, closed, closed_candles(btc_candles or [], now_ms), direction)
    width_pct = (resistance - support) / support * 100
    false_breakouts = count_false_breakouts(range_candles, support, resistance)
    chart_start = max(0, start - 50)
    range_avg = mean(c.turnover for c in range_candles)
    previous_avg = mean(c.turnover for c in prior[-20:]) if prior else range_avg
    return ScanResult(
        ticker=ticker.symbol,
        bybit_url=f"https://www.bybit.com/trade/usdt/{ticker.symbol}",
        price=ticker.last_price,
        change_1h_pct=(
            ((ticker.last_price - ticker.prev_price_1h) / ticker.prev_price_1h) * 100
            if ticker.prev_price_1h
            else None
        ),
        turnover_24h_usd=ticker.turnover_24h_usd,
        turnover_1h_usd=sum(c.turnover for c in closed[-12:]),
        funding_rate=ticker.funding_rate,
        open_interest=ticker.open_interest,
        open_interest_value=ticker.open_interest_value,
        tick_size=tick_size,
        atr_14=atr_value,
        rating=score,
        **{"class": setup_class(score)},
        setup_status="breakout_watch" if metrics["pressure_score"] >= 0.75 else status,
        direction=direction,
        direction_candidate=direction,
        direction_confirmation="v2_structural",
        btc_correlation_5h=btc.correlation,
        btc_correlation_pairs=btc.pairs,
        btc_change_pct_5h=btc.btc_change_pct,
        asset_change_pct_5h=btc.asset_change_pct,
        relative_strength_pct=btc.relative_strength_pct,
        btc_trend=btc.btc_trend,
        btc_signal=btc.signal,
        btc_score_adjustment=btc.score_adjustment,
        rating_with_btc_preview=max(0, min(100, score + btc.score_adjustment)),
        range_candles=len(range_candles),
        range_minutes=len(range_candles) * 5,
        range_width_pct=width_pct,
        resistance_level=resistance,
        support_level=support,
        price_position=position,
        resistance_touches=round(metrics["resistance_touches"]),
        support_touches=round(metrics["support_touches"]),
        false_breakouts=false_breakouts,
        volume_ratio=metrics["volume_ratio"],
        range_turnover_avg=range_avg,
        previous_turnover_avg=previous_avg,
        prev_trend=trend,
        squeeze_score=round(metrics["volatility_contraction"] * 100),
        sideways_confidence=round(metrics["boundary_stability"] * 100),
        sideways_quality="strong" if score >= 85 else "medium",
        flat_range_pct=width_pct,
        flat_slope_rel=metrics["range_slope"],
        flat_r_squared=0.0,
        adx_14=0.0,
        close_inside_ratio=metrics["close_inside_ratio"],
        body_inside_ratio=metrics["body_inside_ratio"],
        trend_alignment=alignment,
        chart_candles=to_chart_candles(closed[chart_start:]),
        ml_candles=to_chart_candles(prior + range_candles, limit=None),
        range_start_timestamp=closed[start].timestamp,
        range_end_timestamp=closed[-1].timestamp,
        trend_start_timestamp=closed[max(0, start - 50)].timestamp,
        trend_end_timestamp=closed[max(0, start - 1)].timestamp,
        trade_plan_status=canonical_plan.status if canonical_plan is not None else "NOT_APPLICABLE",
        trade_plan_reason=canonical_plan.reason if canonical_plan is not None else None,
        trade_plan_version=canonical_plan.version if canonical_plan is not None else None,
        entry_price=canonical_plan.entry_price if canonical_plan is not None else None,
        stop_loss=canonical_plan.stop_loss if canonical_plan is not None else None,
        take_profit=canonical_plan.target_3r if canonical_plan is not None else None,
        risk_price=canonical_plan.risk_price if canonical_plan is not None else None,
        reward_risk=reward_risk,
        shelf_start_timestamp=None,
        shelf_end_timestamp=None,
        trade_plan_variants=plans,
        reasons=[
            f"V2 stable range: {len(range_candles)} candles",
            f"boundary stability: {metrics['boundary_stability']:.2f}",
            f"volatility contraction: {metrics['volatility_contraction']:.2f}",
            f"preceding trend: {trend}",
        ],
        warnings=[] if false_breakouts == 0 else [f"false breakouts: {false_breakouts}"],
    )

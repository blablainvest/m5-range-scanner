from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Optional

from .config import config
from .models import Candle, ChartCandle, ScanResult, Ticker


@dataclass
class LevelCluster:
    level: float
    points: list[float]


@dataclass
class RangeCandidate:
    window: int
    range_start_index: int
    range_end_index: int
    trend_start_index: int
    trend_end_index: int
    support: float
    resistance: float
    support_touches: int
    resistance_touches: int
    false_breakouts: int
    width_pct: float
    price_position: float
    candles: list[Candle]
    score: int
    direction: str
    direction_candidate: str
    direction_confirmation: str
    setup_status: str
    prev_trend: str
    squeeze_score: int
    volume_ratio: float
    turnover_1h_usd: float
    range_turnover_avg: float
    previous_turnover_avg: float
    sideways_confidence: int
    sideways_quality: str
    flat_range_pct: float
    flat_slope_rel: float
    flat_r_squared: float
    adx_14: float
    close_inside_ratio: float
    body_inside_ratio: float
    trend_alignment: str
    reasons: list[str]
    warnings: list[str]


@dataclass
class SidewaysMetrics:
    confidence: int
    quality: str
    flat_range_pct: float
    flat_slope_rel: float
    flat_r_squared: float
    adx_14: float
    close_inside_ratio: float
    body_inside_ratio: float


def closed_candles(candles: list[Candle], now_ms: int) -> list[Candle]:
    if not candles:
        return []
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    if now_ms < ordered[-1].timestamp + 5 * 60 * 1000:
        return ordered[:-1]
    return ordered


def is_local_high(candles: list[Candle], index: int, lookback: int = 2) -> bool:
    if index < lookback or index >= len(candles) - lookback:
        return False
    current = candles[index].high
    return all(candles[index - step].high < current and candles[index + step].high < current for step in range(1, lookback + 1))


def is_local_low(candles: list[Candle], index: int, lookback: int = 2) -> bool:
    if index < lookback or index >= len(candles) - lookback:
        return False
    current = candles[index].low
    return all(candles[index - step].low > current and candles[index + step].low > current for step in range(1, lookback + 1))


def cluster_levels(values: list[float], tick_size: float) -> list[LevelCluster]:
    if not values:
        return []
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters:
            clusters.append([value])
            continue
        current_level = mean(clusters[-1])
        tolerance = max(current_level * config.level_tolerance_pct / 100, tick_size * config.level_tolerance_min_ticks)
        if abs(value - current_level) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [LevelCluster(level=mean(points), points=points) for points in clusters]


def count_independent_zone_touches(candles: list[Candle], support: float, resistance: float, side: str) -> int:
    width = resistance - support
    if width <= 0:
        return 0

    outside_required = config.independent_touch_outside_candles
    touches = 0
    armed = True
    outside_count = 0
    upper_boundary = resistance - width * config.touch_zone_ratio
    lower_boundary = support + width * config.touch_zone_ratio
    for candle in candles:
        if side == "resistance":
            touched = candle.high >= upper_boundary
        elif side == "support":
            touched = candle.low <= lower_boundary
        else:
            raise ValueError(f"unknown touch side: {side}")

        if touched:
            if armed:
                touches += 1
                armed = False
            outside_count = 0
            continue

        outside_count += 1
        if outside_count >= outside_required:
            armed = True
    return touches


def count_false_breakouts(candles: list[Candle], support: float, resistance: float) -> int:
    return sum(1 for candle in candles if candle.close < support or candle.close > resistance)


def range_width_pct(support: float, resistance: float) -> float:
    if support <= 0:
        return 0
    return ((resistance - support) / support) * 100


def price_position(price: float, support: float, resistance: float) -> float:
    width = resistance - support
    if width <= 0:
        return 0.5
    return max(0.0, min(1.0, (price - support) / width))


def linear_regression_metrics(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return 0.0, 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(n)) or 1
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    intercept = y_mean - slope * x_mean
    predicted = [slope * index + intercept for index in range(n)]
    total_sum_squares = sum((value - y_mean) ** 2 for value in values)
    residual_sum_squares = sum((value - prediction) ** 2 for value, prediction in zip(values, predicted))
    r_squared = 1 - residual_sum_squares / total_sum_squares if total_sum_squares else 0.0
    slope_rel = slope / y_mean if y_mean else 0.0
    return slope_rel, max(0.0, min(1.0, r_squared))


def adx_14(candles: list[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 100.0

    true_ranges: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        high_move = current.high - previous.high
        low_move = previous.low - current.low
        plus_dm.append(high_move if high_move > low_move and high_move > 0 else 0.0)
        minus_dm.append(low_move if low_move > high_move and low_move > 0 else 0.0)
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )

    smoothed_tr = sum(true_ranges[:period])
    smoothed_plus_dm = sum(plus_dm[:period])
    smoothed_minus_dm = sum(minus_dm[:period])

    def directional_index(tr_value: float, plus_value: float, minus_value: float) -> float:
        if tr_value <= 0:
            return 0.0
        plus_di = 100 * plus_value / tr_value
        minus_di = 100 * minus_value / tr_value
        di_sum = plus_di + minus_di
        return 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0

    dx_values = [directional_index(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm)]
    for index in range(period, len(true_ranges)):
        smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[index]
        smoothed_plus_dm = smoothed_plus_dm - smoothed_plus_dm / period + plus_dm[index]
        smoothed_minus_dm = smoothed_minus_dm - smoothed_minus_dm / period + minus_dm[index]
        dx_values.append(directional_index(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm))

    if not dx_values:
        return 0.0
    if len(dx_values) < period:
        return mean(dx_values)

    adx = mean(dx_values[:period])
    for dx_value in dx_values[period:]:
        adx = ((adx * (period - 1)) + dx_value) / period
    return adx


def inside_ratios(candles: list[Candle], support: float, resistance: float) -> tuple[float, float]:
    if not candles:
        return 0.0, 0.0
    close_inside = sum(1 for candle in candles if support <= candle.close <= resistance) / len(candles)
    body_inside = sum(
        1
        for candle in candles
        if support <= min(candle.open, candle.close) and max(candle.open, candle.close) <= resistance
    ) / len(candles)
    return close_inside, body_inside


def sideways_quality(confidence: int) -> str:
    if confidence >= 80:
        return "strong"
    if confidence >= 65:
        return "medium"
    return "weak"


def sideways_metrics(candles: list[Candle], support: float, resistance: float, adx_source: list[Candle]) -> SidewaysMetrics:
    high_max = max(candle.high for candle in candles)
    low_min = min(candle.low for candle in candles)
    close_last = candles[-1].close
    flat_range = ((high_max - low_min) / close_last) * 100 if close_last else 0.0
    slope_rel, r_squared = linear_regression_metrics([candle.close for candle in candles])
    adx_value = adx_14(adx_source)
    close_inside, body_inside = inside_ratios(candles, support, resistance)

    confidence = 0
    if flat_range <= 1.0:
        confidence += 25
    elif flat_range <= config.sideways_range_pct_max:
        confidence += 18
    elif flat_range <= 2.0:
        confidence += 8

    abs_slope = abs(slope_rel)
    if abs_slope <= config.sideways_slope_abs_max * 0.5:
        confidence += 20
    elif abs_slope <= config.sideways_slope_abs_max:
        confidence += 14

    if r_squared <= 0.1:
        confidence += 20
    elif r_squared <= 0.2:
        confidence += 15
    elif r_squared <= config.sideways_r_squared_max:
        confidence += 10

    if adx_value < 15:
        confidence += 15
    elif adx_value < 20:
        confidence += 11
    elif adx_value < config.sideways_adx_max:
        confidence += 7

    if close_inside >= 0.95:
        confidence += 10
    elif close_inside >= config.close_inside_ratio_min:
        confidence += 7

    if body_inside >= 0.9:
        confidence += 10
    elif body_inside >= config.body_inside_ratio_min:
        confidence += 7

    confidence = min(confidence, 100)
    return SidewaysMetrics(
        confidence=confidence,
        quality=sideways_quality(confidence),
        flat_range_pct=flat_range,
        flat_slope_rel=slope_rel,
        flat_r_squared=r_squared,
        adx_14=adx_value,
        close_inside_ratio=close_inside,
        body_inside_ratio=body_inside,
    )


def is_valid_sideways(metrics: SidewaysMetrics) -> bool:
    return (
        metrics.flat_range_pct <= config.sideways_range_pct_max
        and abs(metrics.flat_slope_rel) <= config.sideways_slope_abs_max
        and metrics.flat_r_squared <= config.sideways_r_squared_max
        and metrics.close_inside_ratio >= config.close_inside_ratio_min
    )


def previous_trend(candles: list[Candle]) -> str:
    if len(candles) < 10:
        return "neutral"
    closes = [candle.close for candle in candles[-50:]]
    n = len(closes)
    x_mean = (n - 1) / 2
    y_mean = mean(closes)
    denominator = sum((i - x_mean) ** 2 for i in range(n)) or 1
    slope = sum((i - x_mean) * (close - y_mean) for i, close in enumerate(closes)) / denominator
    slope_pct = (slope / y_mean) * 100 if y_mean else 0
    swing_highs = [candles[i].high for i in range(2, len(candles) - 2) if is_local_high(candles, i)]
    swing_lows = [candles[i].low for i in range(2, len(candles) - 2) if is_local_low(candles, i)]
    highs_up = len(swing_highs) >= 2 and swing_highs[-1] > swing_highs[-2]
    lows_up = len(swing_lows) >= 2 and swing_lows[-1] > swing_lows[-2]
    highs_down = len(swing_highs) >= 2 and swing_highs[-1] < swing_highs[-2]
    lows_down = len(swing_lows) >= 2 and swing_lows[-1] < swing_lows[-2]
    if slope_pct > 0.01 and (highs_up or lows_up):
        return "bullish"
    if slope_pct < -0.01 and (highs_down or lows_down):
        return "bearish"
    if slope_pct > 0.015:
        return "neutral-bullish"
    if slope_pct < -0.015:
        return "neutral-bearish"
    return "neutral"


def squeeze_score(candles: list[Candle], support: float, resistance: float, direction_hint: str, tick_size: float) -> int:
    recent = candles[-7:] if len(candles) >= 7 else candles
    if len(recent) < 5:
        return 0
    range_size = resistance - support
    if range_size <= 0:
        return 0
    score = 0
    tolerance = max(resistance * config.level_tolerance_pct / 100, tick_size * config.level_tolerance_min_ticks)

    if direction_hint == "LONG":
        lows = [candle.low for candle in recent]
        near_boundary = [candle for candle in recent if resistance - candle.close <= range_size * 0.25]
        boundary_tests = [candle for candle in recent if abs(candle.high - resistance) <= tolerance]
        pullbacks = [(resistance - candle.low) / range_size for candle in recent]
        if lows[-1] > lows[0] and sum(1 for a, b in zip(lows, lows[1:]) if b >= a) >= 4:
            score += 25
        if len(near_boundary) >= max(3, len(recent) // 2):
            score += 25
        if len(boundary_tests) >= 2:
            score += 20
        if pullbacks[-1] <= pullbacks[0]:
            score += 15
    elif direction_hint == "SHORT":
        highs = [candle.high for candle in recent]
        near_boundary = [candle for candle in recent if candle.close - support <= range_size * 0.25]
        boundary_tests = [candle for candle in recent if abs(candle.low - support) <= tolerance]
        pullbacks = [(candle.high - support) / range_size for candle in recent]
        if highs[-1] < highs[0] and sum(1 for a, b in zip(highs, highs[1:]) if b <= a) >= 4:
            score += 25
        if len(near_boundary) >= max(3, len(recent) // 2):
            score += 25
        if len(boundary_tests) >= 2:
            score += 20
        if pullbacks[-1] <= pullbacks[0]:
            score += 15

    recent_turnover = mean([candle.turnover for candle in recent[-3:]])
    previous_turnover = mean([candle.turnover for candle in recent[:-3]]) if len(recent) > 3 else recent_turnover
    if previous_turnover and recent_turnover >= previous_turnover * 0.9:
        score += 15
    return min(score, 100)


def turnover_metrics(all_closed: list[Candle], range_start_index: int, range_candles: list[Candle]) -> tuple[float, float, float, float]:
    turnover_1h = sum(candle.turnover for candle in all_closed[-12:])
    range_avg = mean([candle.turnover for candle in range_candles]) if range_candles else 0
    previous = all_closed[max(0, range_start_index - 20) : range_start_index]
    previous_avg = mean([candle.turnover for candle in previous]) if previous else range_avg
    ratio = range_avg / previous_avg if previous_avg else 0
    return turnover_1h, range_avg, previous_avg, ratio


def to_chart_candles(candles: list[Candle]) -> list[ChartCandle]:
    return [
        ChartCandle(
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            turnover=candle.turnover,
        )
        for candle in candles[-80:]
    ]


def setup_rating(
    sideways_confidence: int,
    sideways_quality_value: str,
    position: float,
    trend_alignment: str,
    squeeze: int,
    volume_ratio: float,
    false_breakouts: int,
    adx_value: float,
    body_inside_ratio: float,
    support_touches: int,
    resistance_touches: int,
) -> int:
    score = 0
    flat_score = round(min(sideways_confidence, 100) * 0.18)
    if adx_value < 20:
        flat_score += 4
    elif adx_value < config.sideways_adx_max:
        flat_score += 2

    if body_inside_ratio >= 0.75:
        flat_score += 4
    elif body_inside_ratio >= config.body_inside_ratio_min:
        flat_score += 2

    min_touches = min(support_touches, resistance_touches)
    if min_touches >= 3:
        flat_score += 4
    elif min_touches >= 2:
        flat_score += 2
    score += min(flat_score, 30)

    if trend_alignment == "aligned":
        score += 20
    elif trend_alignment == "neutral":
        score += 8

    if position <= 0.15 or position >= 0.85:
        score += 10
    elif position <= 0.25 or position >= 0.75:
        score += 8
    elif 0.35 <= position <= 0.65:
        score += 2

    score += round(min(squeeze, 100) * 0.15)

    if volume_ratio >= 1.7:
        score += 15
    elif volume_ratio >= 1.5:
        score += 13
    elif volume_ratio >= 1.2:
        score += 10
    elif volume_ratio >= 1.0:
        score += 7
    else:
        score += 2

    if false_breakouts == 0:
        score += 10
    elif false_breakouts == 1:
        score += 6
    elif false_breakouts == 2:
        score += 3

    if sideways_quality_value == "weak":
        score = min(score, 69)
    if trend_alignment == "mismatch":
        score = min(score, 59)
    if false_breakouts > config.max_false_breakouts:
        score = min(score, 59)
    elif false_breakouts > 0:
        score = min(score, 89)
    return min(score, 100)


def setup_class(rating: int) -> str:
    if rating >= 90:
        return "A+"
    if rating >= 80:
        return "A"
    if rating >= 70:
        return "B"
    if rating >= 60:
        return "C"
    return "Weak"


def direction_from_trend(position: float, trend: str) -> tuple[str, str, str]:
    if position >= 0.75:
        if trend in ("bullish", "neutral-bullish"):
            return "LONG", "near_resistance", "aligned"
        if trend in ("bearish", "neutral-bearish"):
            return "NEUTRAL", "trend_mismatch", "mismatch"
        return "NEUTRAL", "range_only", "neutral"
    if position <= 0.25:
        if trend in ("bearish", "neutral-bearish"):
            return "SHORT", "near_support", "aligned"
        if trend in ("bullish", "neutral-bullish"):
            return "NEUTRAL", "trend_mismatch", "mismatch"
        return "NEUTRAL", "range_only", "neutral"
    return "NEUTRAL", "range_only", "neutral"


def confirm_direction(direction_candidate: str, squeeze: int, volume_ratio: float) -> tuple[str, str]:
    if direction_candidate == "NEUTRAL":
        return "NEUTRAL", "not_applicable"

    weak_squeeze = squeeze < 45
    weak_volume = volume_ratio < 1.0
    if weak_squeeze and weak_volume:
        return "NEUTRAL", "weak_squeeze_and_volume"
    if weak_squeeze:
        return "NEUTRAL", "weak_squeeze"
    if weak_volume:
        return "NEUTRAL", "weak_volume"
    return direction_candidate, "confirmed"


def analyze_symbol(
    ticker: Ticker,
    candles: list[Candle],
    tick_size: float,
    min_rating: int,
    include_neutral: bool,
    now_ms: int,
) -> Optional[ScanResult]:
    closed = closed_candles(candles, now_ms)
    if len(closed) < max(config.range_windows) + 30:
        return None

    candidates: list[RangeCandidate] = []
    for window in config.range_windows:
        window_candles = closed[-window:]
        range_start_index = len(closed) - window
        range_end_index = len(closed) - 1
        midpoint = (max(c.high for c in window_candles) + min(c.low for c in window_candles)) / 2
        highs = [window_candles[i].high for i in range(len(window_candles)) if is_local_high(window_candles, i)]
        lows = [window_candles[i].low for i in range(len(window_candles)) if is_local_low(window_candles, i)]

        if len(highs) < 2:
            highs = sorted([candle.high for candle in window_candles], reverse=True)[: max(3, window // 5)]
        if len(lows) < 2:
            lows = sorted([candle.low for candle in window_candles])[: max(3, window // 5)]

        resistance_clusters = [cluster for cluster in cluster_levels([value for value in highs if value >= midpoint], tick_size) if len(cluster.points) >= 1]
        support_clusters = [cluster for cluster in cluster_levels([value for value in lows if value <= midpoint], tick_size) if len(cluster.points) >= 1]

        for resistance_cluster in resistance_clusters:
            for support_cluster in support_clusters:
                support = support_cluster.level
                resistance = resistance_cluster.level
                if support >= resistance:
                    continue
                width_pct = range_width_pct(support, resistance)
                if width_pct < config.min_range_width_pct or width_pct > config.max_range_width_pct:
                    continue
                support_touches = count_independent_zone_touches(window_candles, support, resistance, "support")
                resistance_touches = count_independent_zone_touches(window_candles, support, resistance, "resistance")
                if support_touches < 2 or resistance_touches < 2:
                    continue
                false_breakouts = count_false_breakouts(window_candles, support, resistance)
                metrics = sideways_metrics(window_candles, support, resistance, closed[: range_start_index + window])
                if not is_valid_sideways(metrics):
                    continue

                position = price_position(ticker.last_price, support, resistance)

                prior = closed[max(0, range_start_index - 50) : range_start_index]
                trend_start_index = max(0, range_start_index - 50)
                trend_end_index = max(trend_start_index, range_start_index - 1)
                trend = previous_trend(prior)
                direction_candidate, status, trend_alignment = direction_from_trend(position, trend)
                squeeze = squeeze_score(window_candles, support, resistance, direction_candidate, tick_size)
                turnover_1h, range_avg, prev_avg, vol_ratio = turnover_metrics(closed, range_start_index, window_candles)
                direction, direction_confirmation = confirm_direction(direction_candidate, squeeze, vol_ratio)
                if direction_candidate != "NEUTRAL" and direction_confirmation != "confirmed":
                    status = "range_only"
                if direction != "NEUTRAL" and squeeze >= 60 and vol_ratio >= 1.2:
                    status = "breakout_watch"

                rating = setup_rating(
                    metrics.confidence,
                    metrics.quality,
                    position,
                    trend_alignment,
                    squeeze,
                    vol_ratio,
                    false_breakouts,
                    metrics.adx_14,
                    metrics.body_inside_ratio,
                    support_touches,
                    resistance_touches,
                )

                reasons = [
                    f"{metrics.quality} sideways detected: {window} candles",
                    f"flat confidence: {metrics.confidence}",
                    f"flat range: {metrics.flat_range_pct:.2f}%",
                    f"R2: {metrics.flat_r_squared:.2f}",
                    f"ADX: {metrics.adx_14:.1f}",
                    f"support touches: {support_touches}",
                    f"resistance touches: {resistance_touches}",
                    f"volume ratio: {vol_ratio:.2f}",
                    f"previous trend: {trend}",
                ]
                if trend_alignment == "aligned":
                    reasons.append(f"trend aligned: {trend} -> {direction_candidate}")
                if direction_confirmation == "confirmed":
                    reasons.append("direction confirmed by squeeze and turnover")
                if position >= 0.75:
                    reasons.append("price near resistance")
                elif position <= 0.25:
                    reasons.append("price near support")
                else:
                    reasons.append("price in range body")
                if squeeze >= 60:
                    reasons.append("squeeze detected")

                warnings = []
                if trend_alignment == "mismatch":
                    warnings.append("trend mismatch")
                if trend_alignment == "neutral":
                    warnings.append("previous trend is neutral")
                if direction == "NEUTRAL":
                    warnings.append("direction is neutral")
                if direction_confirmation == "weak_squeeze":
                    warnings.append("direction candidate has weak squeeze")
                elif direction_confirmation == "weak_volume":
                    warnings.append("direction candidate has weak turnover")
                elif direction_confirmation == "weak_squeeze_and_volume":
                    warnings.append("direction candidate has weak squeeze and turnover")
                if false_breakouts:
                    warnings.append(f"false breakouts: {false_breakouts}")
                if metrics.adx_14 >= config.sideways_adx_max:
                    warnings.append("ADX is elevated")
                if metrics.body_inside_ratio < 0.75:
                    warnings.append("bodies not fully inside range")
                if abs(metrics.flat_slope_rel) > config.sideways_slope_abs_max * 0.67:
                    warnings.append("range has mild slope")
                if vol_ratio < 1.2:
                    warnings.append("turnover activity is moderate or weak")

                candidates.append(
                    RangeCandidate(
                        window=window,
                        range_start_index=range_start_index,
                        range_end_index=range_end_index,
                        trend_start_index=trend_start_index,
                        trend_end_index=trend_end_index,
                        support=support,
                        resistance=resistance,
                        support_touches=support_touches,
                        resistance_touches=resistance_touches,
                        false_breakouts=false_breakouts,
                        width_pct=width_pct,
                        price_position=position,
                        candles=window_candles,
                        score=rating,
                        direction=direction,
                        direction_candidate=direction_candidate,
                        direction_confirmation=direction_confirmation,
                        setup_status=status,
                        prev_trend=trend,
                        squeeze_score=squeeze,
                        volume_ratio=vol_ratio,
                        turnover_1h_usd=turnover_1h,
                        range_turnover_avg=range_avg,
                        previous_turnover_avg=prev_avg,
                        sideways_confidence=metrics.confidence,
                        sideways_quality=metrics.quality,
                        flat_range_pct=metrics.flat_range_pct,
                        flat_slope_rel=metrics.flat_slope_rel,
                        flat_r_squared=metrics.flat_r_squared,
                        adx_14=metrics.adx_14,
                        close_inside_ratio=metrics.close_inside_ratio,
                        body_inside_ratio=metrics.body_inside_ratio,
                        trend_alignment=trend_alignment,
                        reasons=reasons,
                        warnings=warnings,
                    )
                )

    eligible = [candidate for candidate in candidates if candidate.score >= min_rating]
    if not include_neutral:
        eligible = [candidate for candidate in eligible if candidate.direction != "NEUTRAL"]
    if not eligible:
        return None

    best = sorted(
        eligible,
        key=lambda candidate: (
            candidate.score,
            candidate.sideways_confidence,
            candidate.squeeze_score,
            candidate.volume_ratio,
            -candidate.false_breakouts,
            candidate.resistance_touches + candidate.support_touches,
        ),
        reverse=True,
    )[0]
    change_1h = None
    if ticker.prev_price_1h and ticker.prev_price_1h > 0:
        change_1h = ((ticker.last_price - ticker.prev_price_1h) / ticker.prev_price_1h) * 100
    chart_start_index = max(0, best.trend_start_index, len(closed) - 80)
    chart_candles = to_chart_candles(closed[chart_start_index : best.range_end_index + 1])

    return ScanResult(
        ticker=ticker.symbol,
        bybit_url=f"https://www.bybit.com/trade/usdt/{ticker.symbol}",
        price=ticker.last_price,
        change_1h_pct=change_1h,
        turnover_24h_usd=ticker.turnover_24h_usd,
        turnover_1h_usd=best.turnover_1h_usd,
        rating=best.score,
        setup_class=setup_class(best.score),
        setup_status=best.setup_status,
        direction=best.direction,
        direction_candidate=best.direction_candidate,
        direction_confirmation=best.direction_confirmation,
        range_candles=best.window,
        range_minutes=best.window * 5,
        range_width_pct=best.width_pct,
        resistance_level=best.resistance,
        support_level=best.support,
        price_position=best.price_position,
        resistance_touches=best.resistance_touches,
        support_touches=best.support_touches,
        false_breakouts=best.false_breakouts,
        volume_ratio=best.volume_ratio,
        range_turnover_avg=best.range_turnover_avg,
        previous_turnover_avg=best.previous_turnover_avg,
        prev_trend=best.prev_trend,
        squeeze_score=best.squeeze_score,
        sideways_confidence=best.sideways_confidence,
        sideways_quality=best.sideways_quality,
        flat_range_pct=best.flat_range_pct,
        flat_slope_rel=best.flat_slope_rel,
        flat_r_squared=best.flat_r_squared,
        adx_14=best.adx_14,
        close_inside_ratio=best.close_inside_ratio,
        body_inside_ratio=best.body_inside_ratio,
        trend_alignment=best.trend_alignment,
        chart_candles=chart_candles,
        range_start_timestamp=closed[best.range_start_index].timestamp,
        range_end_timestamp=closed[best.range_end_index].timestamp,
        trend_start_timestamp=closed[best.trend_start_index].timestamp,
        trend_end_timestamp=closed[best.trend_end_index].timestamp,
        reasons=best.reasons,
        warnings=best.warnings,
    )

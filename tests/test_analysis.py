from backend.app.analysis import (
    analyze_symbol,
    adx_14,
    closed_candles,
    count_independent_zone_touches,
    direction_from_trend,
    is_valid_sideways,
    price_position,
    setup_class,
    setup_rating,
    sideways_metrics,
    to_chart_candles,
)
from backend.app.models import Candle, ScanRequest, ScanResult, Ticker


def candle(timestamp: int, open_price: float = 100, high: float = 101, low: float = 99, close: float = 100) -> Candle:
    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
        turnover=10_000,
    )


def flat_candles(count: int = 18) -> list[Candle]:
    candles = []
    for index in range(count):
        close = 100 + (0.12 if index % 2 else -0.08)
        candles.append(candle(index * 300_000, open_price=100, high=100.35, low=99.65, close=close))
    return candles


def trending_candles(count: int = 18) -> list[Candle]:
    candles = []
    for index in range(count):
        close = 100 + index * 0.4
        candles.append(candle(index * 300_000, open_price=close - 0.15, high=close + 0.25, low=close - 0.25, close=close))
    return candles


def bullish_then_flat_candles() -> list[Candle]:
    candles = []
    for index in range(50):
        close = 95 + index * 0.08
        candles.append(candle(index * 300_000, open_price=close - 0.03, high=close + 0.08, low=close - 0.08, close=close))
    for offset in range(18):
        index = 50 + offset
        close = 100.25 + (0.08 if offset % 2 else -0.06)
        high = 100.7 if offset in (1, 5, 9, 13, 17) else close + 0.08
        low = 99.75 if offset in (2, 7, 11, 15) else close - 0.08
        candles.append(candle(index * 300_000, open_price=close - 0.03, high=high, low=low, close=close))
    return candles


def test_closed_candles_excludes_current_unfinished_m5_candle() -> None:
    candles = [
        candle(0),
        candle(300_000),
        candle(600_000),
    ]

    result = closed_candles(candles, now_ms=650_000)

    assert [item.timestamp for item in result] == [0, 300_000]


def test_price_position_uses_zero_to_one_range_location() -> None:
    assert price_position(price=125, support=100, resistance=200) == 0.25
    assert price_position(price=175, support=100, resistance=200) == 0.75
    assert price_position(price=250, support=100, resistance=200) == 1.0


def test_independent_zone_touches_collapse_consecutive_candles() -> None:
    candles = [
        candle(0, high=100.9, low=99.7),
        candle(300_000, high=101.0, low=99.8),
        candle(600_000, high=100.95, low=99.9),
        candle(900_000, high=100.1, low=99.0),
        candle(1_200_000, high=100.92, low=99.6),
    ]

    assert count_independent_zone_touches(candles, support=99, resistance=101, side="resistance") == 3
    assert count_independent_zone_touches(candles[:3], support=99, resistance=101, side="resistance") == 2


def test_sideways_metrics_accept_horizontal_flat() -> None:
    candles = flat_candles(18)
    metrics = sideways_metrics(candles, support=99.65, resistance=100.35, adx_source=candles)

    assert is_valid_sideways(metrics)
    assert metrics.flat_range_pct <= 2.0
    assert abs(metrics.flat_slope_rel) <= 0.003
    assert metrics.flat_r_squared <= 0.45


def test_sideways_metrics_reject_trending_window_by_r_squared_or_slope() -> None:
    candles = trending_candles(18)
    metrics = sideways_metrics(candles, support=100, resistance=107, adx_source=candles)

    assert metrics.flat_r_squared > 0.3 or abs(metrics.flat_slope_rel) > 0.002
    assert not is_valid_sideways(metrics)


def test_adx_is_available_for_scoring_not_hard_filter() -> None:
    candles = trending_candles(24)

    assert adx_14(candles) >= 25


def test_direction_requires_trend_alignment() -> None:
    assert direction_from_trend(0.9, "bullish") == ("LONG", "near_resistance", "aligned")
    assert direction_from_trend(0.1, "bearish") == ("SHORT", "near_support", "aligned")
    assert direction_from_trend(0.1, "bullish") == ("NEUTRAL", "trend_mismatch", "mismatch")
    assert direction_from_trend(0.9, "bearish") == ("NEUTRAL", "trend_mismatch", "mismatch")


def test_setup_class_thresholds() -> None:
    assert setup_class(93) == "A+"
    assert setup_class(84) == "A"
    assert setup_class(74) == "B"
    assert setup_class(62) == "C"
    assert setup_class(59) == "Weak"


def test_setup_rating_has_no_spread_input_and_caps_false_breakouts() -> None:
    rating = setup_rating(
        sideways_confidence=95,
        sideways_quality_value="strong",
        position=0.9,
        trend_alignment="aligned",
        squeeze=90,
        volume_ratio=1.8,
        false_breakouts=1,
        adx_value=18,
        body_inside_ratio=0.8,
        support_touches=3,
        resistance_touches=3,
    )

    assert rating <= 89
    assert setup_class(rating) != "A+"


def test_setup_rating_caps_weak_flat_and_trend_mismatch() -> None:
    weak_rating = setup_rating(95, "weak", 0.9, "aligned", 100, 2.0, 0, 18, 0.8, 3, 3)
    mismatch_rating = setup_rating(95, "strong", 0.9, "mismatch", 100, 2.0, 0, 18, 0.8, 3, 3)

    assert weak_rating <= 69
    assert mismatch_rating <= 59


def test_setup_rating_penalizes_but_does_not_reject_adx_body_and_two_false_breakouts() -> None:
    rating = setup_rating(
        sideways_confidence=80,
        sideways_quality_value="medium",
        position=0.9,
        trend_alignment="aligned",
        squeeze=70,
        volume_ratio=1.5,
        false_breakouts=2,
        adx_value=34,
        body_inside_ratio=0.62,
        support_touches=2,
        resistance_touches=2,
    )

    assert 60 <= rating <= 89


def test_scan_result_schema_exposes_flat_diagnostics_and_no_spread() -> None:
    fields = set(ScanResult.model_fields)

    assert "spread_pct" not in fields
    assert "spread" not in fields
    assert "sideways_confidence" in fields
    assert "flat_r_squared" in fields
    assert "adx_14" in fields
    assert "chart_candles" in fields
    assert "range_start_timestamp" in fields
    assert "trend_start_timestamp" in fields


def test_scan_request_includes_neutral_by_default() -> None:
    request = ScanRequest()

    assert request.include_neutral is True


def test_chart_candles_are_limited_to_80() -> None:
    candles = [candle(index * 300_000) for index in range(120)]

    result = to_chart_candles(candles)

    assert len(result) == 80
    assert result[0].timestamp == 40 * 300_000


def test_analyze_symbol_exposes_range_and_trend_chart_zones() -> None:
    candles = bullish_then_flat_candles()
    ticker = Ticker(symbol="TESTUSDT", last_price=100.62, turnover_24h_usd=3_000_000)

    result = analyze_symbol(ticker, candles, tick_size=0.01, min_rating=0, include_neutral=True, now_ms=candles[-1].timestamp + 300_000)

    assert result is not None
    assert len(result.chart_candles) <= 80
    assert result.trend_start_timestamp <= result.trend_end_timestamp < result.range_start_timestamp <= result.range_end_timestamp
    assert result.range_candles == 18

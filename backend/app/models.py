from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    force: bool = False
    min_rating: int = Field(default=70, ge=0, le=100)
    include_neutral: bool = False
    max_results: int = Field(default=50, ge=1, le=200)
    turnover_24h_min: float = Field(default=2_000_000, ge=0)


class Candle(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


class Instrument(BaseModel):
    symbol: str
    status: str
    contract_type: str
    quote_coin: str
    tick_size: float
    price_scale: Optional[int] = None


class Ticker(BaseModel):
    symbol: str
    last_price: float
    prev_price_1h: Optional[float] = None
    turnover_24h_usd: float
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    open_interest_value: Optional[float] = None


class ScanResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    bybit_url: str
    price: float
    change_1h_pct: Optional[float]
    turnover_24h_usd: float
    turnover_1h_usd: float
    rating: int
    setup_class: str = Field(alias="class")
    setup_status: str
    direction: str
    range_candles: int
    range_minutes: int
    range_width_pct: float
    resistance_level: float
    support_level: float
    price_position: float
    resistance_touches: int
    support_touches: int
    false_breakouts: int
    volume_ratio: float
    range_turnover_avg: float
    previous_turnover_avg: float
    prev_trend: str
    squeeze_score: int
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


class ScanResponse(BaseModel):
    scan_time: str
    scan_duration_ms: int
    total_symbols: int
    filtered_symbols: int
    analyzed_symbols: int
    symbols_with_errors: int
    signals_found: int
    from_cache: bool
    results: list[ScanResult]

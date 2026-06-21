from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScanRequest(BaseModel):
    force: bool = False
    min_rating: int = Field(default=70, ge=0, le=100)
    include_neutral: bool = True
    max_results: int = Field(default=50, ge=1, le=1000)
    turnover_24h_min: float = Field(default=2_000_000, ge=0)


class Candle(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


class ChartCandle(BaseModel):
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


class TradePlanView(BaseModel):
    version: str
    status: str
    reason: Optional[str] = None
    direction: str
    activation: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_price: Optional[float] = None
    target_1r: Optional[float] = None
    target_2r: Optional[float] = None
    target_3r: Optional[float] = None
    trigger_price: Optional[float] = None
    retest_zone_low: Optional[float] = None
    retest_zone_high: Optional[float] = None


class ScanResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    bybit_url: str
    price: float
    change_1h_pct: Optional[float]
    turnover_24h_usd: float
    turnover_1h_usd: float
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    open_interest_value: Optional[float] = None
    tick_size: float = 0.0
    atr_14: float = 0.0
    rating: int
    setup_class: str = Field(alias="class")
    setup_status: str
    direction: str
    direction_candidate: str
    direction_confirmation: str
    btc_correlation_5h: Optional[float]
    btc_correlation_pairs: int
    btc_change_pct_5h: Optional[float]
    asset_change_pct_5h: Optional[float]
    relative_strength_pct: Optional[float]
    btc_trend: str
    btc_signal: str
    btc_score_adjustment: int
    rating_with_btc_preview: int
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
    chart_candles: list[ChartCandle]
    ml_candles: list[ChartCandle] = Field(default_factory=list)
    range_start_timestamp: int
    range_end_timestamp: int
    trend_start_timestamp: int
    trend_end_timestamp: int
    trade_plan_status: str = "NOT_APPLICABLE"
    trade_plan_reason: Optional[str] = None
    trade_plan_version: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_price: Optional[float] = None
    reward_risk: Optional[float] = None
    shelf_start_timestamp: Optional[int] = None
    shelf_end_timestamp: Optional[int] = None
    trade_plan_variants: list[TradePlanView] = Field(default_factory=list)
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


class HistoryItem(BaseModel):
    id: int
    symbol: str
    direction: str
    first_seen_at: str
    last_seen_at: str
    rating: int
    setup_class: str
    support_level: float
    resistance_level: float
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    reward_risk: Optional[float]
    trade_plan_status: str
    outcome: str
    entered_at: Optional[str]
    resolved_at: Optional[str]
    price_at_deadline: Optional[float]
    mfe_r: Optional[float]
    mae_r: Optional[float]
    ambiguous_intrabar: bool


class HistoryResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[HistoryItem]


class TradePlanResultView(BaseModel):
    horizon_minutes: int
    outcome: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1r: Optional[float] = None
    target_2r: Optional[float] = None
    target_3r: Optional[float] = None
    entered_at: Optional[str] = None
    stopped_at: Optional[str] = None
    hit_1r_at: Optional[str] = None
    hit_2r_at: Optional[str] = None
    hit_3r_at: Optional[str] = None
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None
    ambiguous_intrabar: bool = False


class HistoricalPlanView(TradePlanView):
    id: int
    results: list[TradePlanResultView] = Field(default_factory=list)


class SetupDetailResponse(BaseModel):
    setup: HistoryItem
    detector_version: str
    feature_schema_version: str
    snapshot_id: Optional[int] = None
    result: ScanResult
    plans: list[HistoricalPlanView]

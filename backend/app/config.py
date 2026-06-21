import os

from pydantic import BaseModel


class ScannerConfig(BaseModel):
    bybit_base_url: str = "https://api.bybit.com"
    request_timeout_seconds: float = 10.0
    max_concurrent_requests: int = 8
    delay_between_batches_ms: int = 100
    retry_attempts: int = 3
    retry_backoff_ms: int = 1000
    cache_ttl_seconds: int = 300
    kline_limit: int = 200
    range_windows: tuple[int, ...] = (12, 15, 18, 20, 25, 30)
    min_turnover_24h_usd: float = 2_000_000
    default_min_rating: int = 70
    default_max_results: int = 50
    level_tolerance_pct: float = 0.15
    level_tolerance_min_ticks: int = 3
    min_range_width_pct: float = 0.1
    optimal_range_width_min_pct: float = 0.3
    optimal_range_width_max_pct: float = 1.5
    max_range_width_pct: float = 2.0
    max_false_breakouts: int = 2
    sideways_range_pct_max: float = 2.0
    sideways_slope_abs_max: float = 0.003
    sideways_r_squared_max: float = 0.45
    sideways_adx_max: float = 30
    close_inside_ratio_min: float = 0.75
    body_inside_ratio_min: float = 0.60
    touch_zone_ratio: float = 0.2
    independent_touch_outside_candles: int = 2
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./m5_scanner.db")
    automatic_scan_min_rating: int = int(os.getenv("AUTOMATIC_SCAN_MIN_RATING", "0"))
    automatic_scan_max_results: int = int(os.getenv("AUTOMATIC_SCAN_MAX_RESULTS", "1000"))
    automatic_scan_turnover_min: float = float(os.getenv("AUTOMATIC_SCAN_TURNOVER_MIN", "2000000"))
    scan_interval_minutes: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    schedule_offset_minute_utc: int = int(os.getenv("SCHEDULE_OFFSET_MINUTE_UTC", "2"))
    setup_dedup_minutes: int = int(os.getenv("SETUP_DEDUP_MINUTES", "60"))
    outcome_window_minutes: int = int(os.getenv("OUTCOME_WINDOW_MINUTES", "60"))


config = ScannerConfig()

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from .analysis import analyze_symbol
from .bybit_client import BybitClient
from .config import config
from .detector_v2 import detect_v2
from .models import ScanRequest, ScanResponse, ScanResult


logger = logging.getLogger(__name__)


class ScannerService:
    def __init__(self, bybit: BybitClient) -> None:
        self.bybit = bybit
        self._cache: Optional[ScanResponse] = None
        self._cache_key: Optional[tuple[int, bool, int, float]] = None
        self._cache_created_monotonic: float = 0
        self._scan_lock = asyncio.Lock()
        self.last_background_results: list[ScanResult] = []

    def _request_key(self, request: ScanRequest) -> tuple[int, bool, int, float]:
        return (request.min_rating, request.include_neutral, request.max_results, request.turnover_24h_min)

    def _fresh_cache(self, request: ScanRequest) -> bool:
        return (
            self._cache is not None
            and self._cache_key == self._request_key(request)
            and time.monotonic() - self._cache_created_monotonic < config.cache_ttl_seconds
        )

    async def scan(self, request: ScanRequest) -> ScanResponse:
        if not request.force and self._fresh_cache(request):
            cached = self._cache.model_copy(deep=True)
            cached.from_cache = True
            return cached

        async with self._scan_lock:
            if not request.force and self._fresh_cache(request):
                cached = self._cache.model_copy(deep=True)
                cached.from_cache = True
                return cached
            response = await self._run_scan(request)
            self._cache = response.model_copy(deep=True)
            self._cache_key = self._request_key(request)
            self._cache_created_monotonic = time.monotonic()
            return response

    def _apply_response_filters(self, results: list[ScanResult], request: ScanRequest) -> list[ScanResult]:
        filtered = [
            result
            for result in results
            if result.rating >= request.min_rating
            and result.turnover_24h_usd >= request.turnover_24h_min
            and (request.include_neutral or result.direction != "NEUTRAL")
        ]
        return sorted(filtered, key=lambda result: result.rating, reverse=True)[: request.max_results]

    async def _run_scan(self, request: ScanRequest) -> ScanResponse:
        started = time.perf_counter()
        scan_time = datetime.now(timezone.utc).isoformat()
        logger.info(
            "scan_started min_rating=%s turnover_24h_min=%s max_results=%s force=%s",
            request.min_rating,
            request.turnover_24h_min,
            request.max_results,
            request.force,
        )
        instruments, tickers = await asyncio.gather(self.bybit.instruments(), self.bybit.tickers())
        eligible_instruments = [
            instrument
            for instrument in instruments
            if instrument.status == "Trading"
            and instrument.contract_type == "LinearPerpetual"
            and instrument.quote_coin == "USDT"
            and instrument.symbol in tickers
            and tickers[instrument.symbol].turnover_24h_usd >= request.turnover_24h_min
        ]
        eligible_instruments.sort(key=lambda instrument: tickers[instrument.symbol].turnover_24h_usd, reverse=True)

        try:
            btc_candles = await self.bybit.klines("BTCUSDT")
        except Exception:
            btc_candles = []
            logger.exception("btc_context_unavailable symbol=BTCUSDT endpoint=/v5/market/kline")

        semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        errors = 0
        analyzed = 0
        results: list[ScanResult] = []
        now_ms = int(time.time() * 1000)

        async def process(
            instrument_index: int,
            symbol: str,
            tick_size: float,
        ) -> tuple[Optional[ScanResult], Optional[ScanResult]]:
            nonlocal errors, analyzed
            if instrument_index and instrument_index % config.max_concurrent_requests == 0:
                await asyncio.sleep(config.delay_between_batches_ms / 1000)
            async with semaphore:
                try:
                    candles = btc_candles if symbol == "BTCUSDT" else await self.bybit.klines(symbol)
                    analyzed += 1
                    primary = analyze_symbol(
                        tickers[symbol],
                        candles,
                        tick_size,
                        min_rating=request.min_rating,
                        include_neutral=request.include_neutral,
                        now_ms=now_ms,
                        btc_candles=btc_candles,
                    )
                    background = detect_v2(
                        tickers[symbol],
                        candles,
                        tick_size,
                        now_ms,
                        btc_candles=btc_candles,
                    )
                    return primary, background
                except Exception:
                    errors += 1
                    logger.exception("symbol_analysis_failed symbol=%s endpoint=/v5/market/kline", symbol)
                    return None, None

        tasks = [
            process(index, instrument.symbol, instrument.tick_size)
            for index, instrument in enumerate(eligible_instruments)
        ]
        background_results: list[ScanResult] = []
        for primary, background in await asyncio.gather(*tasks):
            if primary is not None:
                results.append(primary)
            if background is not None:
                background_results.append(background)

        filtered_results = self._apply_response_filters(results, request)
        self.last_background_results = sorted(
            background_results,
            key=lambda result: result.rating,
            reverse=True,
        )
        duration_ms = round((time.perf_counter() - started) * 1000)
        response = ScanResponse(
            scan_time=scan_time,
            scan_duration_ms=duration_ms,
            total_symbols=len(instruments),
            filtered_symbols=len(eligible_instruments),
            analyzed_symbols=analyzed,
            symbols_with_errors=errors,
            signals_found=len(filtered_results),
            from_cache=False,
            results=filtered_results,
        )
        logger.info(
            "scan_completed duration_ms=%s total_symbols=%s filtered_symbols=%s analyzed_symbols=%s errors=%s signals=%s",
            duration_ms,
            len(instruments),
            len(eligible_instruments),
            analyzed,
            errors,
            len(filtered_results),
        )
        return response

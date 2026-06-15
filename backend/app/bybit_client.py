from __future__ import annotations

import asyncio
import logging
from typing import Any
from typing import Optional

import httpx

from .config import config
from .models import Candle, Instrument, Ticker


class BybitError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class BybitClient:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._client = httpx.AsyncClient(
            base_url=config.bybit_base_url,
            timeout=config.request_timeout_seconds,
            headers={"User-Agent": "m5-range-scanner/0.2.0"},
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(config.retry_attempts):
            try:
                response = await self._client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                if payload.get("retCode") != 0:
                    raise BybitError(f"Bybit retCode={payload.get('retCode')}: {payload.get('retMsg')}")
                return payload["result"]
            except (httpx.HTTPError, ValueError, KeyError, BybitError) as exc:
                last_error = exc
                if attempt < config.retry_attempts - 1:
                    logger.warning(
                        "bybit_retry endpoint=%s attempt=%s max_attempts=%s error=%s",
                        path,
                        attempt + 1,
                        config.retry_attempts,
                        exc,
                    )
                    await asyncio.sleep((config.retry_backoff_ms / 1000) * (attempt + 1))
        logger.error(
            "bybit_request_failed endpoint=%s attempts=%s error=%s",
            path,
            config.retry_attempts,
            last_error,
        )
        raise BybitError(str(last_error) if last_error else "unknown Bybit error")

    async def instruments(self) -> list[Instrument]:
        instruments: list[Instrument] = []
        cursor: Optional[str] = None
        while True:
            params: dict[str, Any] = {"category": "linear", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            result = await self._get("/v5/market/instruments-info", params)
            for item in result.get("list", []):
                price_filter = item.get("priceFilter") or {}
                instrument = Instrument(
                    symbol=item.get("symbol", ""),
                    status=item.get("status", ""),
                    contract_type=item.get("contractType", ""),
                    quote_coin=item.get("quoteCoin", ""),
                    tick_size=max(_to_float(price_filter.get("tickSize"), 0.0), 1e-12),
                    price_scale=_to_int(item.get("priceScale")),
                )
                if instrument.symbol:
                    instruments.append(instrument)
            cursor = result.get("nextPageCursor") or None
            if not cursor:
                break
        return instruments

    async def tickers(self) -> dict[str, Ticker]:
        result = await self._get("/v5/market/tickers", {"category": "linear"})
        tickers: dict[str, Ticker] = {}
        for item in result.get("list", []):
            symbol = item.get("symbol", "")
            if not symbol:
                continue
            tickers[symbol] = Ticker(
                symbol=symbol,
                last_price=_to_float(item.get("lastPrice")),
                prev_price_1h=_to_float(item.get("prevPrice1h"), 0.0) or None,
                turnover_24h_usd=_to_float(item.get("turnover24h")),
                funding_rate=_to_float(item.get("fundingRate"), 0.0) or None,
                open_interest=_to_float(item.get("openInterest"), 0.0) or None,
                open_interest_value=_to_float(item.get("openInterestValue"), 0.0) or None,
            )
        return tickers

    async def klines(self, symbol: str) -> list[Candle]:
        result = await self._get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "5", "limit": config.kline_limit},
        )
        candles: list[Candle] = []
        for row in result.get("list", []):
            if len(row) < 7:
                continue
            candles.append(
                Candle(
                    timestamp=int(row[0]),
                    open=_to_float(row[1]),
                    high=_to_float(row[2]),
                    low=_to_float(row[3]),
                    close=_to_float(row[4]),
                    volume=_to_float(row[5]),
                    turnover=_to_float(row[6]),
                )
            )
        return sorted(candles, key=lambda candle: candle.timestamp)

from __future__ import annotations

import httpx
import pytest

from backend.app.bybit_client import BybitClient
from backend.app.config import config
from backend.app.models import Candle, Instrument, ScanRequest, Ticker
from backend.app.scanner import ScannerService


def bybit_response(items: list, next_cursor: str = "") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "retCode": 0,
            "retMsg": "OK",
            "result": {"list": items, "nextPageCursor": next_cursor},
        },
    )


@pytest.mark.asyncio
async def test_bybit_instruments_pagination() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return bybit_response(
                [
                    {
                        "symbol": "AAAUSDT",
                        "status": "Trading",
                        "contractType": "LinearPerpetual",
                        "quoteCoin": "USDT",
                        "priceFilter": {"tickSize": "0.01"},
                    }
                ],
                next_cursor="page-2",
            )
        return bybit_response(
            [
                {
                    "symbol": "BBBUSDT",
                    "status": "Trading",
                    "contractType": "LinearPerpetual",
                    "quoteCoin": "USDT",
                    "priceFilter": {"tickSize": "0.001"},
                }
            ]
        )

    client = BybitClient(transport=httpx.MockTransport(handler))
    try:
        instruments = await client.instruments()
    finally:
        await client.close()

    assert [item.symbol for item in instruments] == ["AAAUSDT", "BBBUSDT"]
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_bybit_tickers_and_klines_normalization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tickers"):
            return bybit_response(
                [
                    {
                        "symbol": "AAAUSDT",
                        "lastPrice": "101.5",
                        "prevPrice1h": "100",
                        "turnover24h": "3500000",
                    }
                ]
            )
        return bybit_response(
            [
                ["600000", "101", "102", "100", "101.5", "20", "2020"],
                ["300000", "100", "101", "99", "100.5", "10", "1000"],
            ]
        )

    client = BybitClient(transport=httpx.MockTransport(handler))
    try:
        tickers = await client.tickers()
        candles = await client.klines("AAAUSDT")
    finally:
        await client.close()

    assert tickers["AAAUSDT"].turnover_24h_usd == 3_500_000
    assert [item.timestamp for item in candles] == [300_000, 600_000]
    assert candles[-1].turnover == 2020


@pytest.mark.asyncio
async def test_bybit_retries_before_success(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="temporarily unavailable")
        return bybit_response([])

    monkeypatch.setattr(config, "retry_backoff_ms", 0)
    client = BybitClient(transport=httpx.MockTransport(handler))
    try:
        assert await client.tickers() == {}
    finally:
        await client.close()

    assert attempts == 3


class FakeBybit:
    def __init__(self, fail_symbol: str | None = None) -> None:
        self.fail_symbol = fail_symbol
        self.instruments_calls = 0
        self.kline_calls: list[str] = []

    async def instruments(self) -> list[Instrument]:
        self.instruments_calls += 1
        return [
            Instrument(
                symbol=symbol,
                status="Trading",
                contract_type="LinearPerpetual",
                quote_coin="USDT",
                tick_size=0.01,
            )
            for symbol in ("AAAUSDT", "BBBUSDT")
        ]

    async def tickers(self) -> dict[str, Ticker]:
        return {
            symbol: Ticker(symbol=symbol, last_price=100, turnover_24h_usd=3_000_000)
            for symbol in ("AAAUSDT", "BBBUSDT")
        }

    async def klines(self, symbol: str) -> list[Candle]:
        self.kline_calls.append(symbol)
        if symbol == self.fail_symbol:
            raise RuntimeError("expected test failure")
        return [
            Candle(
                timestamp=index * 300_000,
                open=100,
                high=100.4,
                low=99.6,
                close=100,
                volume=100,
                turnover=10_000,
            )
            for index in range(80)
        ]


@pytest.mark.asyncio
async def test_scanner_continues_after_partial_symbol_failure() -> None:
    scanner = ScannerService(FakeBybit(fail_symbol="BBBUSDT"))  # type: ignore[arg-type]

    response = await scanner.scan(ScanRequest(min_rating=0, max_results=10))

    assert response.analyzed_symbols == 1
    assert response.symbols_with_errors == 1


@pytest.mark.asyncio
async def test_scanner_cache_and_force() -> None:
    bybit = FakeBybit()
    scanner = ScannerService(bybit)  # type: ignore[arg-type]
    request = ScanRequest(min_rating=0, max_results=10)

    first = await scanner.scan(request)
    second = await scanner.scan(request)
    forced = await scanner.scan(request.model_copy(update={"force": True}))

    assert first.from_cache is False
    assert second.from_cache is True
    assert forced.from_cache is False
    assert bybit.instruments_calls == 2
    assert bybit.kline_calls.count("BTCUSDT") == 2


@pytest.mark.asyncio
async def test_scanner_loads_btc_once_per_uncached_scan() -> None:
    bybit = FakeBybit()
    scanner = ScannerService(bybit)  # type: ignore[arg-type]

    await scanner.scan(ScanRequest(min_rating=0, max_results=10))

    assert bybit.kline_calls.count("BTCUSDT") == 1

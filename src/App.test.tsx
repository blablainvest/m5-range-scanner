import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, SetupChart } from "./App";


function result(overrides: Record<string, unknown> = {}) {
  return {
    ticker: "AAAUSDT",
    bybit_url: "https://www.bybit.com/trade/usdt/AAAUSDT",
    price: 100,
    change_1h_pct: 1,
    turnover_24h_usd: 3_000_000,
    turnover_1h_usd: 100_000,
    rating: 80,
    class: "A",
    setup_status: "breakout_watch",
    direction: "LONG",
    direction_candidate: "LONG",
    direction_confirmation: "confirmed",
    btc_correlation_5h: 0.72,
    btc_correlation_pairs: 60,
    btc_change_pct_5h: 1.2,
    asset_change_pct_5h: 2,
    relative_strength_pct: 0.8,
    btc_trend: "bullish",
    btc_signal: "btc_confirmed",
    btc_score_adjustment: 3,
    rating_with_btc_preview: 83,
    range_candles: 18,
    range_minutes: 90,
    range_width_pct: 1,
    resistance_level: 101,
    support_level: 99,
    price_position: 0.9,
    resistance_touches: 3,
    support_touches: 3,
    false_breakouts: 0,
    volume_ratio: 1.4,
    range_turnover_avg: 10_000,
    previous_turnover_avg: 8_000,
    prev_trend: "bullish",
    squeeze_score: 70,
    sideways_confidence: 85,
    sideways_quality: "strong",
    flat_range_pct: 1,
    flat_slope_rel: 0.0001,
    flat_r_squared: 0.1,
    adx_14: 18,
    close_inside_ratio: 0.9,
    body_inside_ratio: 0.8,
    trend_alignment: "aligned",
    chart_candles: [
      { timestamp: 300_000, open: 100, high: 101, low: 99, close: 100.5, turnover: 10_000 },
      { timestamp: 600_000, open: 100.5, high: 101, low: 100, close: 100.8, turnover: 12_000 }
    ],
    range_start_timestamp: 600_000,
    range_end_timestamp: 600_000,
    trend_start_timestamp: 300_000,
    trend_end_timestamp: 300_000,
    reasons: ["test reason"],
    warnings: [],
    ...overrides
  };
}


function response(results: ReturnType<typeof result>[]) {
  return {
    scan_time: "2026-06-15T12:00:00Z",
    scan_duration_ms: 100,
    total_symbols: results.length,
    filtered_symbols: results.length,
    analyzed_symbols: results.length,
    symbols_with_errors: 0,
    signals_found: results.length,
    from_cache: false,
    results
  };
}


function mockFetch(payload: ReturnType<typeof response>, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status: ok ? 200 : 500,
      json: async () => payload
    })
  );
}


afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});


describe("App", () => {
  it("shows loading and error states", async () => {
    const user = userEvent.setup();
    let resolveRequest: ((value: unknown) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => {
      resolveRequest = resolve;
    })));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Сканировать" }));
    expect(screen.getByText("Сканирование...")).toBeInTheDocument();
    resolveRequest?.({ ok: false, status: 500 });
    expect(await screen.findByText("Ошибка: API вернул 500")).toBeInTheDocument();
  });

  it("sorts numeric ratings and renders direction badges", async () => {
    const user = userEvent.setup();
    mockFetch(response([
      result({ ticker: "LOWUSDT", rating: 70, direction: "NEUTRAL" }),
      result({ ticker: "HIGHUSDT", rating: 90, direction: "LONG" }),
      result({ ticker: "MIDUSDT", rating: 80, direction: "SHORT" })
    ]));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Сканировать" }));
    await screen.findByText("HIGHUSDT");
    const rowsDescending = screen.getAllByRole("row").slice(1);
    expect(within(rowsDescending[0]).getByText("HIGHUSDT")).toBeInTheDocument();
    expect(document.querySelector(".direction.long")).toHaveTextContent("LONG");
    expect(document.querySelector(".direction.short")).toHaveTextContent("SHORT");
    expect(document.querySelector(".direction.neutral")).toHaveTextContent("NEUTRAL");

    await user.click(screen.getByRole("button", { name: "Scoring" }));
    const rowsAscending = screen.getAllByRole("row").slice(1);
    expect(within(rowsAscending[0]).getByText("LOWUSDT")).toBeInTheDocument();
  });

  it("opens the inline setup chart", async () => {
    const user = userEvent.setup();
    mockFetch(response([result()]));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Сканировать" }));
    await user.click(await screen.findByRole("button", { name: "Свой график" }));

    expect(screen.getByRole("img", { name: "Свой график AAAUSDT" })).toBeInTheDocument();
  });

  it("filters direction and class locally without another scan", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response([
        result({ ticker: "LONGAUSDT", direction: "LONG", class: "A" }),
        result({ ticker: "SHORTBUSDT", direction: "SHORT", direction_candidate: "SHORT", class: "B" })
      ])
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Сканировать" }));
    await screen.findByText("LONGAUSDT");
    await user.click(screen.getByRole("button", { name: "LONG" }));

    expect(screen.queryByText("LONGAUSDT")).not.toBeInTheDocument();
    expect(screen.getByText("SHORTBUSDT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Сбросить" }));
    expect(screen.getByText("LONGAUSDT")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "B" }));
    expect(screen.getByText("LONGAUSDT")).toBeInTheDocument();
    expect(screen.queryByText("SHORTBUSDT")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});


describe("SetupChart", () => {
  it("shows a fallback when candles are absent", () => {
    render(<SetupChart result={result({ chart_candles: [] }) as never} />);

    expect(screen.getByText("Нет свечей для встроенного графика.")).toBeInTheDocument();
  });
});

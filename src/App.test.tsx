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
      { timestamp: 300_000, open: 100, high: 101, low: 99, close: 100.5, volume: 100, turnover: 10_000 },
      { timestamp: 600_000, open: 100.5, high: 101, low: 100, close: 100.8, volume: 120, turnover: 12_000 }
    ],
    range_start_timestamp: 600_000,
    range_end_timestamp: 600_000,
    trend_start_timestamp: 300_000,
    trend_end_timestamp: 300_000,
    trade_plan_status: "READY",
    trade_plan_reason: null,
    trade_plan_version: "wick-shelf-v1",
    entry_price: 101,
    stop_loss: 100.2,
    take_profit: 103.4,
    risk_price: 0.8,
    reward_risk: 3,
    shelf_start_timestamp: 300_000,
    shelf_end_timestamp: 600_000,
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
      result({ ticker: "LOWUSDT", rating: 70, direction: "LONG" }),
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

  it("opens history, shows outcomes and exposes the filtered XLSX export", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          page: 1,
          page_size: 50,
          total: 1,
          items: [{
            id: 1,
            symbol: "AAAUSDT",
            direction: "LONG",
            first_seen_at: "2026-06-15T12:02:00Z",
            last_seen_at: "2026-06-15T12:02:00Z",
            rating: 80,
            setup_class: "A",
            support_level: 99,
            resistance_level: 101,
            entry_price: 0.01234567,
            stop_loss: 0.01198765,
            take_profit: 0.01345678,
            reward_risk: 3,
            trade_plan_status: "READY",
            outcome: "PENDING",
            entered_at: "2026-06-15T12:10:00Z",
            resolved_at: "2026-06-15T12:35:00Z",
            price_at_deadline: 103.4,
            mfe_r: 3,
            mae_r: 0.2,
            ambiguous_intrabar: false
          }]
        })
      })
    );
    render(<App />);

    await user.click(screen.getByRole("button", { name: "История" }));

    expect(await screen.findByText("Ожидает / в работе", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByText("Таймаут")).not.toBeInTheDocument();
    expect(screen.queryByText("TIMEOUT")).not.toBeInTheDocument();
    expect(screen.getByText("AAAUSDT")).toBeInTheDocument();
    expect(screen.getByText("0.01234567")).toBeInTheDocument();
    expect(screen.getByText("0.01198765")).toBeInTheDocument();
    expect(screen.getByText("0.01345678")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Скачать XLSX" })).toHaveAttribute(
      "href",
      `${window.location.origin}/api/history/export.xlsx?`
    );
  });
});


describe("SetupChart", () => {
  it("shows a fallback when candles are absent", () => {
    render(<SetupChart result={result({ chart_candles: [] }) as never} />);

    expect(screen.getByText("Нет свечей для встроенного графика.")).toBeInTheDocument();
  });

  it("switches between plan variants and labels trade levels", async () => {
    const user = userEvent.setup();
    render(<SetupChart result={result({
      trade_plan_variants: [
        {
          version: "wick-shelf-v1", status: "INVALID", reason: "no shelf", direction: "LONG",
          activation: "boundary_touch", entry_price: 101, stop_loss: null, risk_price: null,
          target_1r: null, target_2r: null, target_3r: null, trigger_price: 101,
          retest_zone_low: null, retest_zone_high: null
        },
        {
          version: "breakout-buffer-v2", status: "READY", reason: null, direction: "LONG",
          activation: "price_crosses_buffer", entry_price: 101.1, stop_loss: 100.5, risk_price: 0.6,
          target_1r: 101.7, target_2r: 102.3, target_3r: 102.9, trigger_price: 101.1,
          retest_zone_low: null, retest_zone_high: null
        }
      ]
    }) as never} />);

    expect(screen.getByText("no shelf")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "V2" }));
    expect(screen.getByText("breakout-buffer-v2")).toBeInTheDocument();
    expect(screen.getByText(/3R 102.9/)).toBeInTheDocument();
  });
});

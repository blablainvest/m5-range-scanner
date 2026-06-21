import React from "react";
import { ArrowDown, ArrowUp, Clock3, Download, ExternalLink, Radar, RefreshCw, Search } from "lucide-react";

type Direction = "LONG" | "SHORT" | "NEUTRAL";
type SetupClass = "A+" | "A" | "B" | "C" | "Weak";
type SortKey = "ticker" | "rating" | "turnover_24h_usd" | "price_position" | "volume_ratio" | "range_width_pct" | "sideways_confidence";
type SortDirection = "asc" | "desc";

type TradePlan = {
  version: string;
  status: string;
  reason: string | null;
  direction: Direction;
  activation: string;
  entry_price: number | null;
  stop_loss: number | null;
  risk_price: number | null;
  target_1r: number | null;
  target_2r: number | null;
  target_3r: number | null;
  trigger_price: number | null;
  retest_zone_low: number | null;
  retest_zone_high: number | null;
};

type ScanResult = {
  ticker: string;
  bybit_url: string;
  price: number;
  change_1h_pct: number | null;
  turnover_24h_usd: number;
  turnover_1h_usd: number;
  rating: number;
  class: SetupClass;
  setup_status: string;
  direction: Direction;
  direction_candidate: Direction;
  direction_confirmation: string;
  btc_correlation_5h: number | null;
  btc_correlation_pairs: number;
  btc_change_pct_5h: number | null;
  asset_change_pct_5h: number | null;
  relative_strength_pct: number | null;
  btc_trend: string;
  btc_signal: string;
  btc_score_adjustment: number;
  rating_with_btc_preview: number;
  range_candles: number;
  range_minutes: number;
  range_width_pct: number;
  resistance_level: number;
  support_level: number;
  price_position: number;
  resistance_touches: number;
  support_touches: number;
  false_breakouts: number;
  volume_ratio: number;
  range_turnover_avg: number;
  previous_turnover_avg: number;
  prev_trend: string;
  squeeze_score: number;
  sideways_confidence: number;
  sideways_quality: string;
  flat_range_pct: number;
  flat_slope_rel: number;
  flat_r_squared: number;
  adx_14: number;
  close_inside_ratio: number;
  body_inside_ratio: number;
  trend_alignment: string;
  chart_candles: ChartCandle[];
  range_start_timestamp: number;
  range_end_timestamp: number;
  trend_start_timestamp: number;
  trend_end_timestamp: number;
  trade_plan_status: string;
  trade_plan_reason: string | null;
  trade_plan_version: string | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_price: number | null;
  reward_risk: number | null;
  shelf_start_timestamp: number | null;
  shelf_end_timestamp: number | null;
  trade_plan_variants: TradePlan[];
  reasons: string[];
  warnings: string[];
};

type ChartCandle = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover: number;
};

type ScanResponse = {
  scan_time: string;
  scan_duration_ms: number;
  total_symbols: number;
  filtered_symbols: number;
  analyzed_symbols: number;
  symbols_with_errors: number;
  signals_found: number;
  from_cache: boolean;
  results: ScanResult[];
};

type HistoryItem = {
  id: number;
  symbol: string;
  direction: Direction;
  first_seen_at: string;
  last_seen_at: string;
  rating: number;
  setup_class: SetupClass;
  support_level: number;
  resistance_level: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  reward_risk: number | null;
  trade_plan_status: string;
  outcome: string;
  entered_at: string | null;
  resolved_at: string | null;
  price_at_deadline: number | null;
  mfe_r: number | null;
  mae_r: number | null;
  ambiguous_intrabar: boolean;
};

type HistoryResponse = {
  page: number;
  page_size: number;
  total: number;
  items: HistoryItem[];
};

type SetupDetail = {
  setup: HistoryItem;
  detector_version: string;
  feature_schema_version: string;
  snapshot_id: number | null;
  result: ScanResult;
  plans: TradePlan[];
};

const numberFormatters = new Map<number, Intl.NumberFormat>();
const compactFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2
});
const allDirections: Direction[] = ["LONG", "SHORT"];
const allClasses: SetupClass[] = ["A+", "A", "B", "C", "Weak"];
const btcSignalLabels: Record<string, string> = {
  own_strength: "Own strength",
  own_weakness: "Own weakness",
  btc_confirmed: "BTC confirms",
  btc_driven: "BTC-driven",
  independent: "Independent",
  btc_headwind: "BTC headwind",
  mixed: "Mixed",
  insufficient: "Insufficient"
};
const outcomeLabels: Record<string, string> = {
  PENDING: "Ожидает / в работе"
};

function formatUsd(value: number) {
  return `$${compactFormatter.format(value)}`;
}

function formatNumber(value: number, digits = 2) {
  const normalizedDigits = Math.max(0, Math.min(20, digits));
  let formatter = numberFormatters.get(normalizedDigits);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: normalizedDigits });
    numberFormatters.set(normalizedDigits, formatter);
  }
  return formatter.format(Number(value.toFixed(normalizedDigits)));
}

function formatOptionalNumber(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : formatNumber(value, digits);
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function formatOutcome(value: string) {
  return outcomeLabels[value] ?? value;
}

function formatSigned(value: number) {
  return `${value > 0 ? "+" : ""}${value}`;
}

function classNameForDirection(direction: Direction) {
  if (direction === "LONG") return "direction long";
  if (direction === "SHORT") return "direction short";
  return "direction neutral";
}

function apiUrl(path: string) {
  return new URL(path, `${window.location.origin}/`).toString();
}

export function App() {
  const [activeView, setActiveView] = React.useState<"scanner" | "history">("scanner");
  const [data, setData] = React.useState<ScanResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sortKey, setSortKey] = React.useState<SortKey>("rating");
  const [sortDirection, setSortDirection] = React.useState<SortDirection>("desc");
  const [minRating, setMinRating] = React.useState(70);
  const [turnoverMin, setTurnoverMin] = React.useState(2_000_000);
  const [directionFilters, setDirectionFilters] = React.useState<Direction[]>(allDirections);
  const [classFilters, setClassFilters] = React.useState<SetupClass[]>(allClasses);
  const [expandedTicker, setExpandedTicker] = React.useState<string | null>(null);
  const [chartTicker, setChartTicker] = React.useState<string | null>(null);

  async function runScan(force = false) {
    setLoading(true);
    setError(null);
    setExpandedTicker(null);
    setChartTicker(null);
    try {
      const response = await fetch(apiUrl("/api/scan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          force,
          min_rating: minRating,
          max_results: 80,
          turnover_24h_min: turnoverMin
        })
      });
      if (!response.ok) {
        throw new Error(`API вернул ${response.status}`);
      }
      const payload = (await response.json()) as ScanResponse;
      setData(payload);
    } catch (scanError) {
      setError(scanError instanceof Error ? scanError.message : "Не удалось выполнить сканирование");
    } finally {
      setLoading(false);
    }
  }

  function updateSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection(nextKey === "ticker" ? "asc" : "desc");
  }

  function toggleDirection(direction: Direction) {
    setDirectionFilters((current) => (
      current.includes(direction)
        ? current.filter((item) => item !== direction)
        : [...current, direction]
    ));
  }

  function toggleClass(setupClass: SetupClass) {
    setClassFilters((current) => (
      current.includes(setupClass)
        ? current.filter((item) => item !== setupClass)
        : [...current, setupClass]
    ));
  }

  function resetLocalFilters() {
    setDirectionFilters(allDirections);
    setClassFilters(allClasses);
  }

  const filteredResults = React.useMemo(() => {
    const results = data?.results ?? [];
    return results.filter(
      (result) => directionFilters.includes(result.direction) && classFilters.includes(result.class)
    );
  }, [classFilters, data, directionFilters]);

  const sortedResults = React.useMemo(() => {
    return [...filteredResults].sort((a, b) => {
      const aValue = a[sortKey];
      const bValue = b[sortKey];
      const comparison =
        typeof aValue === "string" && typeof bValue === "string"
          ? aValue.localeCompare(bValue)
          : Number(aValue) - Number(bValue);
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [filteredResults, sortDirection, sortKey]);

  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">5M</span>
          <div>
            <strong>Range Scanner</strong>
            <small>Phase II</small>
          </div>
        </div>
        <nav aria-label="Основная навигация">
          <button className={activeView === "scanner" ? "nav-item active" : "nav-item"} onClick={() => setActiveView("scanner")}>
            <Radar size={18} />
            Сканер
          </button>
          <button className={activeView === "history" ? "nav-item active" : "nav-item"} onClick={() => setActiveView("history")}>
            <Clock3 size={18} />
            История
          </button>
        </nav>
        <div className="sidebar-note">
          <span>Автоскан</span>
          <strong>каждые 15 минут</strong>
        </div>
      </aside>
      <main className="app-shell">
      {activeView === "scanner" ? (
      <>
      <header className="topbar">
        <div>
          <h1>M5 Range Scanner</h1>
          <p>Bybit USDT perpetual futures, M5 ranges and squeeze candidates.</p>
        </div>
        <div className="actions">
          <button className="scan-button secondary" onClick={() => runScan(true)} disabled={loading} title="Запустить новое сканирование без кэша">
            <RefreshCw size={17} />
            Force
          </button>
          <button className="scan-button" onClick={() => runScan(false)} disabled={loading}>
            {loading ? <RefreshCw className="spin" size={18} /> : <Search size={18} />}
            {loading ? "Сканирование..." : "Сканировать"}
          </button>
        </div>
      </header>

      <section className="controls" aria-label="Фильтры">
        <label>
          Минимальный скоринг
          <input type="number" min="0" max="100" value={minRating} onChange={(event) => setMinRating(Number(event.target.value))} />
        </label>
        <label>
          24ч Объем
          <input type="number" min="0" step="100000" value={turnoverMin} onChange={(event) => setTurnoverMin(Number(event.target.value))} />
        </label>
        <FilterGroup
          label="Direction"
          values={allDirections}
          selected={directionFilters}
          onToggle={toggleDirection}
        />
        <FilterGroup
          label="Class"
          values={allClasses}
          selected={classFilters}
          onToggle={toggleClass}
        />
        <button className="reset-filters" onClick={resetLocalFilters} type="button">
          <RefreshCw size={14} />
          Сбросить
        </button>
      </section>

      <section className="status-line" aria-live="polite">
        {error && <span className="error">Ошибка: {error}</span>}
        {!error && !data && !loading && <span>Нажмите `Сканировать`, чтобы получить текущие setup.</span>}
        {loading && <span>Загрузка инструментов, свечей и расчет setup...</span>}
        {data && !loading && (
          <span>
            {data.from_cache ? "Данные из кэша" : "Новое сканирование"}: показано {filteredResults.length} из {data.results.length}, analyzed {data.analyzed_symbols} / filtered {data.filtered_symbols}, {formatNumber(data.scan_duration_ms / 1000, 1)} sec.
          </span>
        )}
      </section>

      <section className="table-wrap">
        <table>
          <thead>
            <tr>
              <SortableHeader label="Ticker" active={sortKey === "ticker"} direction={sortDirection} onClick={() => updateSort("ticker")} />
              <SortableHeader label="Scoring" active={sortKey === "rating"} direction={sortDirection} onClick={() => updateSort("rating")} />
              <SortableHeader label="24h Volume" active={sortKey === "turnover_24h_usd"} direction={sortDirection} onClick={() => updateSort("turnover_24h_usd")} />
              <SortableHeader label="Position 0-1" active={sortKey === "price_position"} direction={sortDirection} onClick={() => updateSort("price_position")} />
              <th>Direction</th>
              <th>Status</th>
              <th>Class</th>
              <SortableHeader label="Flat" active={sortKey === "sideways_confidence"} direction={sortDirection} onClick={() => updateSort("sideways_confidence")} />
              <SortableHeader label="Volume Ratio" active={sortKey === "volume_ratio"} direction={sortDirection} onClick={() => updateSort("volume_ratio")} />
              <SortableHeader label="Range Width" active={sortKey === "range_width_pct"} direction={sortDirection} onClick={() => updateSort("range_width_pct")} />
              <th>BTC Context</th>
              <th>BTC Preview</th>
              <th>ТВХ</th>
              <th>СЛ</th>
              <th>ТП</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedResults.map((result) => (
              <React.Fragment key={result.ticker}>
                <tr className="result-row" onClick={() => setExpandedTicker(expandedTicker === result.ticker ? null : result.ticker)}>
                  <td>
                    <a href={result.bybit_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="ticker-link">
                      {result.ticker}
                      <ExternalLink size={14} />
                    </a>
                  </td>
                  <td className="numeric rating">{result.rating}</td>
                  <td className="numeric">{formatUsd(result.turnover_24h_usd)}</td>
                  <td className="numeric">{formatNumber(result.price_position, 3)}</td>
                  <td><span className={classNameForDirection(result.direction)}>{result.direction}</span></td>
                  <td>{result.setup_status}</td>
                  <td><span className="setup-class">{result.class}</span></td>
                  <td><span className={`flat-badge ${result.sideways_quality}`}>{result.sideways_quality} {result.sideways_confidence}</span></td>
                  <td className="numeric">{formatNumber(result.volume_ratio, 2)}x</td>
                  <td className="numeric">{formatNumber(result.range_width_pct, 2)}%</td>
                  <td>
                    <div className={`btc-context ${result.btc_signal}`}>
                      <span>{btcSignalLabels[result.btc_signal] ?? result.btc_signal}</span>
                      <small>
                        corr {formatOptionalNumber(result.btc_correlation_5h, 2)} · rel {formatOptionalNumber(result.relative_strength_pct, 2)}%
                      </small>
                    </div>
                  </td>
                  <td className="numeric">
                    {result.rating_with_btc_preview}
                    <span className={`score-adjustment ${result.btc_score_adjustment < 0 ? "negative" : ""}`}>
                      {formatSigned(result.btc_score_adjustment)}
                    </span>
                  </td>
                  <td className="numeric">{result.entry_price == null ? "—" : formatNumber(result.entry_price, 8)}</td>
                  <td className="numeric stop-value">{result.stop_loss == null ? "—" : formatNumber(result.stop_loss, 8)}</td>
                  <td className="numeric take-value">{result.take_profit == null ? "—" : formatNumber(result.take_profit, 8)}</td>
                  <td>
                    <button
                      className="chart-button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setChartTicker(chartTicker === result.ticker ? null : result.ticker);
                        setExpandedTicker(null);
                      }}
                    >
                      Свой график
                    </button>
                  </td>
                </tr>
                {chartTicker === result.ticker && (
                  <tr className="chart-row">
                    <td colSpan={16}>
                      <SetupChart result={result} />
                    </td>
                  </tr>
                )}
                {expandedTicker === result.ticker && (
                  <tr className="details-row">
                    <td colSpan={16}>
                      <div className="details-grid">
                        <Metric label="Trade plan" value={result.trade_plan_status} />
                        <Metric label="ТВХ / СЛ / ТП" value={`${formatOptionalNumber(result.entry_price, 8)} / ${formatOptionalNumber(result.stop_loss, 8)} / ${formatOptionalNumber(result.take_profit, 8)}`} />
                        <Metric label="Risk / RR" value={`${formatOptionalNumber(result.risk_price, 8)} / ${formatOptionalNumber(result.reward_risk, 1)}`} />
                        <Metric label="Plan reason" value={result.trade_plan_reason ?? "ready"} />
                        <Metric label="Support" value={formatNumber(result.support_level, 8)} />
                        <Metric label="Resistance" value={formatNumber(result.resistance_level, 8)} />
                        <Metric label="Touches R/S" value={`${result.resistance_touches}/${result.support_touches}`} />
                        <Metric label="Prev trend" value={result.prev_trend} />
                        <Metric label="Trend alignment" value={result.trend_alignment} />
                        <Metric label="Direction candidate" value={result.direction_candidate} />
                        <Metric label="Confirmation" value={result.direction_confirmation} />
                        <Metric label="Squeeze" value={String(result.squeeze_score)} />
                        <Metric label="1h turnover" value={formatUsd(result.turnover_1h_usd)} />
                        <Metric label="Flat range" value={`${formatNumber(result.flat_range_pct, 2)}%`} />
                        <Metric label="R2" value={formatNumber(result.flat_r_squared, 3)} />
                        <Metric label="ADX" value={formatNumber(result.adx_14, 1)} />
                        <Metric label="Slope" value={formatNumber(result.flat_slope_rel, 5)} />
                        <Metric label="Inside close/body" value={`${formatNumber(result.close_inside_ratio, 2)} / ${formatNumber(result.body_inside_ratio, 2)}`} />
                        <Metric label="False breakouts" value={String(result.false_breakouts)} />
                        <Metric label="BTC correlation" value={formatOptionalNumber(result.btc_correlation_5h, 3)} />
                        <Metric label="BTC pairs" value={String(result.btc_correlation_pairs)} />
                        <Metric label="BTC / Asset 5h" value={`${formatOptionalNumber(result.btc_change_pct_5h, 2)}% / ${formatOptionalNumber(result.asset_change_pct_5h, 2)}%`} />
                        <Metric label="Relative BTC" value={`${formatOptionalNumber(result.relative_strength_pct, 2)}%`} />
                        <Metric label="BTC signal" value={btcSignalLabels[result.btc_signal] ?? result.btc_signal} />
                        <Metric label="Rating preview" value={`${result.rating} -> ${result.rating_with_btc_preview} (${formatSigned(result.btc_score_adjustment)})`} />
                      </div>
                      <div className="reason-columns">
                        <ListBlock title="Reasons" items={result.reasons} />
                        <ListBlock title="Warnings" items={result.warnings.length ? result.warnings : ["no warnings"]} />
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
            {!loading && sortedResults.length === 0 && (
              <tr>
                <td colSpan={16} className="empty-state">
                  {data ? "Setup не найдены с текущими фильтрами." : "Результаты появятся здесь после сканирования."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
      </>
      ) : (
        <HistoryView />
      )}
      </main>
    </div>
  );
}

function HistoryView() {
  const [data, setData] = React.useState<HistoryResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [symbol, setSymbol] = React.useState("");
  const [direction, setDirection] = React.useState("");
  const [outcome, setOutcome] = React.useState("");
  const [minRating, setMinRating] = React.useState("");
  const [dateFrom, setDateFrom] = React.useState("");
  const [dateTo, setDateTo] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [expandedId, setExpandedId] = React.useState<number | null>(null);
  const [detail, setDetail] = React.useState<SetupDetail | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  function queryParams(includePage = true) {
    const params = new URLSearchParams();
    if (symbol.trim()) params.set("symbol", symbol.trim());
    if (direction) params.set("direction", direction);
    if (outcome) params.set("outcome", outcome);
    if (minRating) params.set("min_rating", minRating);
    if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00Z`);
    if (dateTo) params.set("date_to", `${dateTo}T23:59:59Z`);
    if (includePage) {
      params.set("page", String(page));
      params.set("page_size", "50");
    }
    return params;
  }

  async function loadHistory() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl(`/api/history?${queryParams().toString()}`));
      if (!response.ok) throw new Error(`API вернул ${response.status}`);
      setData((await response.json()) as HistoryResponse);
    } catch (historyError) {
      setError(historyError instanceof Error ? historyError.message : "Не удалось загрузить историю");
    } finally {
      setLoading(false);
    }
  }

  async function toggleDetail(setupId: number) {
    if (expandedId === setupId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(setupId);
    setDetail(null);
    setDetailLoading(true);
    try {
      const response = await fetch(apiUrl(`/api/history/${setupId}`));
      if (!response.ok) throw new Error(`API вернул ${response.status}`);
      setDetail((await response.json()) as SetupDetail);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "Не удалось загрузить график");
    } finally {
      setDetailLoading(false);
    }
  }

  React.useEffect(() => {
    void loadHistory();
  }, [page]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    if (page !== 1) {
      setPage(1);
    } else {
      void loadHistory();
    }
  }

  const exportUrl = apiUrl(`/api/history/export.xlsx?${queryParams(false).toString()}`);
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / 50));

  return (
    <>
      <header className="topbar">
        <div>
          <h1>История сетапов</h1>
          <p>Все обнаруженные диапазоны, торговые планы и результат первого часа.</p>
        </div>
        <div className="actions">
          <a className="scan-button secondary export-button" href={apiUrl("/api/ml/export.parquet")}>
            <Download size={17} />
            ML Parquet
          </a>
          <a className="scan-button export-button" href={exportUrl}>
            <Download size={17} />
            Скачать XLSX
          </a>
        </div>
      </header>

      <form className="controls history-controls" onSubmit={applyFilters}>
        <label>
          Монета
          <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} placeholder="BTCUSDT" />
        </label>
        <label>
          Направление
          <select value={direction} onChange={(event) => setDirection(event.target.value)}>
            <option value="">Все</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
            <option value="NEUTRAL">NEUTRAL (архив)</option>
          </select>
        </label>
        <label>
          Исход
          <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
            <option value="">Все</option>
            <option value="PENDING">Ожидает / в работе</option>
            <option value="NO_TRADE">Без сделки</option>
            <option value="STOP">Стоп</option>
            <option value="TAKE">Тейк</option>
            <option value="NOT_APPLICABLE">Без плана</option>
          </select>
        </label>
        <label>
          Рейтинг от
          <input type="number" min="0" max="100" value={minRating} onChange={(event) => setMinRating(event.target.value)} />
        </label>
        <label>
          От
          <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label>
          До
          <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </label>
        <button className="scan-button history-submit" type="submit" disabled={loading}>
          <Search size={16} />
          Применить
        </button>
      </form>

      <section className="status-line">
        {error && <span className="error">Ошибка: {error}</span>}
        {!error && loading && <span>Загрузка истории...</span>}
        {!error && !loading && <span>Найдено сетапов: {data?.total ?? 0}</span>}
      </section>

      <section className="table-wrap history-table">
        <table>
          <thead>
            <tr>
              <th>Время</th>
              <th>Монета</th>
              <th>Direction</th>
              <th>Rating</th>
              <th>ТВХ</th>
              <th>СЛ</th>
              <th>ТП</th>
              <th>RR</th>
              <th>План</th>
              <th>Исход</th>
              <th>Вход</th>
              <th>MFE / MAE</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((item) => (
              <React.Fragment key={item.id}>
              <tr className="result-row" onClick={() => void toggleDetail(item.id)}>
                <td>{formatDate(item.first_seen_at)}</td>
                <td>
                  <a className="ticker-link" href={`https://www.bybit.com/trade/usdt/${item.symbol}`} target="_blank" rel="noreferrer">
                    {item.symbol}
                    <ExternalLink size={13} />
                  </a>
                </td>
                <td><span className={classNameForDirection(item.direction)}>{item.direction}</span></td>
                <td className="numeric rating">{item.rating} <span className="history-class">{item.setup_class}</span></td>
                <td className="numeric">{formatOptionalNumber(item.entry_price, 8)}</td>
                <td className="numeric stop-value">{formatOptionalNumber(item.stop_loss, 8)}</td>
                <td className="numeric take-value">{formatOptionalNumber(item.take_profit, 8)}</td>
                <td className="numeric">{formatOptionalNumber(item.reward_risk, 1)}</td>
                <td><span className={`plan-status ${item.trade_plan_status.toLowerCase()}`}>{item.trade_plan_status}</span></td>
                <td>
                  <span className={`outcome ${item.outcome.toLowerCase()}`}>{formatOutcome(item.outcome)}</span>
                  {item.ambiguous_intrabar && <small className="ambiguous-note">M1: стоп при конфликте</small>}
                </td>
                <td>{formatDate(item.entered_at)}</td>
                <td className="numeric">{formatOptionalNumber(item.mfe_r, 2)} / {formatOptionalNumber(item.mae_r, 2)}</td>
              </tr>
              {expandedId === item.id && (
                <tr className="chart-row">
                  <td colSpan={12}>
                    {detailLoading && <div className="chart-fallback">Загрузка снимка и моделей...</div>}
                    {!detailLoading && detail?.setup.id === item.id && <SetupChart result={detail.result} />}
                  </td>
                </tr>
              )}
              </React.Fragment>
            ))}
            {!loading && (data?.items.length ?? 0) === 0 && (
              <tr><td colSpan={12} className="empty-state">История с такими фильтрами пока пуста.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      <div className="pagination">
        <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => current - 1)}>Назад</button>
        <span>Страница {page} из {totalPages}</span>
        <button type="button" disabled={page >= totalPages || loading} onClick={() => setPage((current) => current + 1)}>Далее</button>
      </div>
    </>
  );
}

export function SetupChart({ result }: { result: ScanResult }) {
  const candles = result.chart_candles;
  const fallbackPlan: TradePlan = {
    version: result.trade_plan_version ?? "wick-shelf-v1",
    status: result.trade_plan_status,
    reason: result.trade_plan_reason,
    direction: result.direction,
    activation: "boundary_touch",
    entry_price: result.entry_price,
    stop_loss: result.stop_loss,
    risk_price: result.risk_price,
    target_1r: result.risk_price == null || result.entry_price == null
      ? null
      : result.direction === "LONG" ? result.entry_price + result.risk_price : result.entry_price - result.risk_price,
    target_2r: result.risk_price == null || result.entry_price == null
      ? null
      : result.direction === "LONG" ? result.entry_price + result.risk_price * 2 : result.entry_price - result.risk_price * 2,
    target_3r: result.take_profit,
    trigger_price: result.entry_price,
    retest_zone_low: null,
    retest_zone_high: null
  };
  const plans = result.trade_plan_variants?.length ? result.trade_plan_variants : [fallbackPlan];
  const [selectedVersion, setSelectedVersion] = React.useState(plans[0].version);
  React.useEffect(() => {
    setSelectedVersion(plans[0].version);
  }, [result.ticker, result.range_end_timestamp]);
  const plan = plans.find((item) => item.version === selectedVersion) ?? plans[0];

  if (!candles.length) {
    return <div className="chart-fallback">Нет свечей для встроенного графика.</div>;
  }

  const width = 1180;
  const height = 360;
  const pad = { top: 22, right: 170, bottom: 34, left: 54 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const planPrices = [
    plan.entry_price,
    plan.stop_loss,
    plan.target_1r,
    plan.target_2r,
    plan.target_3r,
    plan.trigger_price,
    plan.retest_zone_low,
    plan.retest_zone_high
  ].filter((value): value is number => value != null);
  const minLow = Math.min(...candles.map((candle) => candle.low), result.support_level, ...planPrices);
  const maxHigh = Math.max(...candles.map((candle) => candle.high), result.resistance_level, ...planPrices);
  const yPadding = (maxHigh - minLow) * 0.08 || maxHigh * 0.001 || 1;
  const yMin = minLow - yPadding;
  const yMax = maxHigh + yPadding;
  const xStep = plotWidth / Math.max(candles.length - 1, 1);
  const candleBodyWidth = Math.max(3, Math.min(9, xStep * 0.58));

  function xForIndex(index: number) {
    return pad.left + index * xStep;
  }

  function yForPrice(price: number) {
    return pad.top + ((yMax - price) / (yMax - yMin)) * plotHeight;
  }

  function indexForTimestamp(timestamp: number) {
    const exact = candles.findIndex((candle) => candle.timestamp === timestamp);
    if (exact >= 0) return exact;
    let nearest = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    candles.forEach((candle, index) => {
      const distance = Math.abs(candle.timestamp - timestamp);
      if (distance < bestDistance) {
        bestDistance = distance;
        nearest = index;
      }
    });
    return nearest;
  }

  const rangeStart = indexForTimestamp(result.range_start_timestamp);
  const rangeEnd = indexForTimestamp(result.range_end_timestamp);
  const trendStart = indexForTimestamp(result.trend_start_timestamp);
  const trendEnd = Math.min(indexForTimestamp(result.trend_end_timestamp), Math.max(rangeStart - 1, 0));
  const trendStartCandle = candles[trendStart];
  const trendEndCandle = candles[trendEnd] ?? trendStartCandle;
  const trendColor = result.direction === "LONG" ? "#27d17f" : result.direction === "SHORT" ? "#f0445a" : "#9aa6b2";
  const supportY = yForPrice(result.support_level);
  const resistanceY = yForPrice(result.resistance_level);
  const rangeX = xForIndex(rangeStart) - candleBodyWidth;
  const rangeW = Math.max(candleBodyWidth * 2, xForIndex(rangeEnd) - xForIndex(rangeStart) + candleBodyWidth * 2);
  const rangeY = Math.min(resistanceY, supportY);
  const rangeH = Math.max(2, Math.abs(supportY - resistanceY));
  const trendX = xForIndex(trendStart) - candleBodyWidth;
  const trendW = Math.max(candleBodyWidth * 2, xForIndex(trendEnd) - xForIndex(trendStart) + candleBodyWidth * 2);
  const shelfStart = result.shelf_start_timestamp == null ? null : indexForTimestamp(result.shelf_start_timestamp);
  const shelfEnd = result.shelf_end_timestamp == null ? null : indexForTimestamp(result.shelf_end_timestamp);
  const zoneX = Math.max(rangeX, xForIndex(rangeEnd));
  const zoneWidth = width - pad.right - zoneX;
  const entryY = plan.entry_price == null ? null : yForPrice(plan.entry_price);
  const stopY = plan.stop_loss == null ? null : yForPrice(plan.stop_loss);
  const target3Y = plan.target_3r == null ? null : yForPrice(plan.target_3r);
  const levels = [
    { label: "ТВХ", price: plan.entry_price, className: "entry-line" },
    { label: "СЛ", price: plan.stop_loss, className: "stop-line" },
    { label: "1R", price: plan.target_1r, className: "take-line target-1r" },
    { label: "2R", price: plan.target_2r, className: "take-line target-2r" },
    { label: "3R", price: plan.target_3r, className: "take-line target-3r" }
  ];

  return (
    <div className="chart-panel">
      <div className="chart-header">
        <div>
          <strong>{result.ticker}</strong>
          <span>{result.direction} · {result.prev_trend} · {result.trend_alignment}</span>
        </div>
        <div className="chart-header-actions">
          <div className="plan-switcher" aria-label="Модель торгового плана">
            {plans.map((item, index) => (
              <button
                key={item.version}
                type="button"
                aria-pressed={item.version === plan.version}
                onClick={() => setSelectedVersion(item.version)}
              >
                V{index + 1}
              </button>
            ))}
          </div>
          <span className={`plan-status ${plan.status.toLowerCase()}`}>{plan.status}</span>
          <span className={`flat-badge ${result.sideways_quality}`}>{result.sideways_quality} {result.sideways_confidence}</span>
        </div>
      </div>
      <svg className="setup-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Свой график ${result.ticker}`}>
        <rect x={0} y={0} width={width} height={height} rx={8} fill="#11161f" />
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = pad.top + plotHeight * ratio;
          return <line key={ratio} x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="grid-line" />;
        })}
        <rect x={trendX} y={pad.top} width={trendW} height={plotHeight} className="trend-zone" />
        <rect x={rangeX} y={rangeY} width={rangeW} height={rangeH} className="range-zone" />
        {shelfStart !== null && shelfEnd !== null && (
          <rect
            x={xForIndex(shelfStart) - candleBodyWidth}
            y={rangeY}
            width={Math.max(candleBodyWidth * 2, xForIndex(shelfEnd) - xForIndex(shelfStart) + candleBodyWidth * 2)}
            height={rangeH}
            className="shelf-zone"
          />
        )}
        {entryY !== null && stopY !== null && (
          <rect
            x={zoneX}
            y={Math.min(entryY, stopY)}
            width={zoneWidth}
            height={Math.max(2, Math.abs(entryY - stopY))}
            className="risk-zone"
          />
        )}
        {entryY !== null && target3Y !== null && (
          <rect
            x={zoneX}
            y={Math.min(entryY, target3Y)}
            width={zoneWidth}
            height={Math.max(2, Math.abs(entryY - target3Y))}
            className="reward-zone"
          />
        )}
        {plan.retest_zone_low != null && plan.retest_zone_high != null && (
          <rect
            x={zoneX}
            y={yForPrice(plan.retest_zone_high)}
            width={zoneWidth}
            height={Math.max(2, yForPrice(plan.retest_zone_low) - yForPrice(plan.retest_zone_high))}
            className="retest-zone"
          />
        )}
        <line x1={pad.left} x2={width - pad.right} y1={resistanceY} y2={resistanceY} className="resistance-line" />
        <line x1={pad.left} x2={width - pad.right} y1={supportY} y2={supportY} className="support-line" />
        {plan.trigger_price != null && plan.activation === "two_m5_closes_then_retest" && (
          <line x1={zoneX} x2={width - pad.right} y1={yForPrice(plan.trigger_price)} y2={yForPrice(plan.trigger_price)} className="trigger-line" />
        )}
        {levels.map((level) => level.price == null ? null : (
          <g key={level.label}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={yForPrice(level.price)}
              y2={yForPrice(level.price)}
              className={level.className}
            />
            <text x={width - pad.right + 10} y={yForPrice(level.price) + 4} className={`chart-level-label ${level.className}`}>
              {level.label} {formatNumber(level.price, 8)}
            </text>
          </g>
        ))}
        <line
          x1={xForIndex(trendStart)}
          y1={yForPrice(trendStartCandle.close)}
          x2={xForIndex(trendEnd)}
          y2={yForPrice(trendEndCandle.close)}
          stroke={trendColor}
          strokeWidth={2}
          strokeDasharray="5 4"
          opacity={0.85}
        />
        {candles.map((candle, index) => {
          const x = xForIndex(index);
          const isUp = candle.close >= candle.open;
          const bodyTop = yForPrice(Math.max(candle.open, candle.close));
          const bodyBottom = yForPrice(Math.min(candle.open, candle.close));
          const bodyHeight = Math.max(2, bodyBottom - bodyTop);
          return (
            <g key={candle.timestamp}>
              <line x1={x} x2={x} y1={yForPrice(candle.high)} y2={yForPrice(candle.low)} stroke={isUp ? "#28c77b" : "#f05260"} strokeWidth={1} opacity={0.75} />
              <rect x={x - candleBodyWidth / 2} y={bodyTop} width={candleBodyWidth} height={bodyHeight} rx={1.5} fill={isUp ? "#28c77b" : "#f05260"} opacity={0.9} />
            </g>
          );
        })}
        <text x={width - pad.right + 10} y={resistanceY + 4} className="chart-label">R {formatNumber(result.resistance_level, 6)}</text>
        <text x={width - pad.right + 10} y={supportY + 4} className="chart-label">S {formatNumber(result.support_level, 6)}</text>
        <text x={pad.left} y={height - 12} className="chart-label">trend context</text>
        <text x={xForIndex(rangeStart)} y={height - 12} className="chart-label">detected range</text>
      </svg>
      <div className="plan-summary">
        <strong>{plan.version}</strong>
        <span>{plan.activation}</span>
        {plan.reason && <span className={plan.status === "INVALID" ? "error" : ""}>{plan.reason}</span>}
      </div>
      <div className="chart-diagnostics">
        <Metric label="R2" value={formatNumber(result.flat_r_squared, 3)} />
        <Metric label="ADX" value={formatNumber(result.adx_14, 1)} />
        <Metric label="Slope" value={formatNumber(result.flat_slope_rel, 5)} />
        <Metric label="Inside close/body" value={`${formatNumber(result.close_inside_ratio, 2)} / ${formatNumber(result.body_inside_ratio, 2)}`} />
        <Metric label="False breakouts" value={String(result.false_breakouts)} />
        <Metric label="Range candles" value={String(result.range_candles)} />
        <Metric label="Trade plan" value={plan.status} />
        <Metric label="ТВХ / СЛ / 3R" value={`${formatOptionalNumber(plan.entry_price, 8)} / ${formatOptionalNumber(plan.stop_loss, 8)} / ${formatOptionalNumber(plan.target_3r, 8)}`} />
        <Metric label="Risk" value={formatOptionalNumber(plan.risk_price, 8)} />
        <Metric label="BTC correlation" value={formatOptionalNumber(result.btc_correlation_5h, 3)} />
        <Metric label="Relative BTC" value={`${formatOptionalNumber(result.relative_strength_pct, 2)}%`} />
        <Metric label="BTC signal" value={btcSignalLabels[result.btc_signal] ?? result.btc_signal} />
        <Metric label="Rating preview" value={`${result.rating} -> ${result.rating_with_btc_preview}`} />
      </div>
      <div className="reason-columns">
        <ListBlock title="Reasons" items={result.reasons} />
        <ListBlock title="Warnings" items={result.warnings.length ? result.warnings : ["no warnings"]} />
      </div>
    </div>
  );
}

function FilterGroup<T extends string>({
  label,
  values,
  selected,
  onToggle
}: {
  label: string;
  values: T[];
  selected: T[];
  onToggle: (value: T) => void;
}) {
  return (
    <div className="filter-group" aria-label={label}>
      <span>{label}</span>
      <div className="filter-options">
        {values.map((value) => (
          <button
            key={value}
            type="button"
            className="filter-chip"
            aria-pressed={selected.includes(value)}
            onClick={() => onToggle(value)}
          >
            {value}
          </button>
        ))}
      </div>
    </div>
  );
}

function SortableHeader({ label, active, direction, onClick }: { label: string; active: boolean; direction: SortDirection; onClick: () => void }) {
  return (
    <th>
      <button className="sort-button" onClick={onClick}>
        {label}
        {active ? direction === "asc" ? <ArrowUp size={14} /> : <ArrowDown size={14} /> : null}
      </button>
    </th>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

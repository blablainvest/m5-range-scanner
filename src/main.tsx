import React from "react";
import ReactDOM from "react-dom/client";
import { ArrowDown, ArrowUp, ExternalLink, RefreshCw, Search } from "lucide-react";
import "./styles.css";

type Direction = "LONG" | "SHORT" | "NEUTRAL";
type SortKey = "ticker" | "rating" | "turnover_24h_usd" | "price_position" | "volume_ratio" | "range_width_pct" | "sideways_confidence";
type SortDirection = "asc" | "desc";

type ScanResult = {
  ticker: string;
  bybit_url: string;
  price: number;
  change_1h_pct: number | null;
  turnover_24h_usd: number;
  turnover_1h_usd: number;
  rating: number;
  class: string;
  setup_status: string;
  direction: Direction;
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
  reasons: string[];
  warnings: string[];
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

const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const compactFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2
});

function formatUsd(value: number) {
  return `$${compactFormatter.format(value)}`;
}

function formatNumber(value: number, digits = 2) {
  return numberFormatter.format(Number(value.toFixed(digits)));
}

function classNameForDirection(direction: Direction) {
  if (direction === "LONG") return "direction long";
  if (direction === "SHORT") return "direction short";
  return "direction neutral";
}

function App() {
  const [data, setData] = React.useState<ScanResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sortKey, setSortKey] = React.useState<SortKey>("rating");
  const [sortDirection, setSortDirection] = React.useState<SortDirection>("desc");
  const [minRating, setMinRating] = React.useState(70);
  const [includeNeutral, setIncludeNeutral] = React.useState(false);
  const [turnoverMin, setTurnoverMin] = React.useState(2_000_000);
  const [expandedTicker, setExpandedTicker] = React.useState<string | null>(null);

  async function runScan(force = false) {
    setLoading(true);
    setError(null);
    setExpandedTicker(null);
    try {
      const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          force,
          min_rating: minRating,
          include_neutral: includeNeutral,
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

  const sortedResults = React.useMemo(() => {
    const results = data?.results ?? [];
    return [...results].sort((a, b) => {
      const aValue = a[sortKey];
      const bValue = b[sortKey];
      const comparison =
        typeof aValue === "string" && typeof bValue === "string"
          ? aValue.localeCompare(bValue)
          : Number(aValue) - Number(bValue);
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [data, sortDirection, sortKey]);

  return (
    <main className="app-shell">
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
          Min rating
          <input type="number" min="0" max="100" value={minRating} onChange={(event) => setMinRating(Number(event.target.value))} />
        </label>
        <label>
          24h turnover min
          <input type="number" min="0" step="100000" value={turnoverMin} onChange={(event) => setTurnoverMin(Number(event.target.value))} />
        </label>
        <label className="toggle">
          <input type="checkbox" checked={includeNeutral} onChange={(event) => setIncludeNeutral(event.target.checked)} />
          Include neutral
        </label>
      </section>

      <section className="status-line" aria-live="polite">
        {error && <span className="error">Ошибка: {error}</span>}
        {!error && !data && !loading && <span>Нажмите `Сканировать`, чтобы получить текущие setup.</span>}
        {loading && <span>Загрузка инструментов, свечей и расчет setup...</span>}
        {data && !loading && (
          <span>
            {data.from_cache ? "Данные из кэша" : "Новое сканирование"}: {data.signals_found} setup, analyzed {data.analyzed_symbols} / filtered {data.filtered_symbols}, {formatNumber(data.scan_duration_ms / 1000, 1)} sec.
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
                </tr>
                {expandedTicker === result.ticker && (
                  <tr className="details-row">
                    <td colSpan={10}>
                      <div className="details-grid">
                        <Metric label="Support" value={formatNumber(result.support_level, 8)} />
                        <Metric label="Resistance" value={formatNumber(result.resistance_level, 8)} />
                        <Metric label="Touches R/S" value={`${result.resistance_touches}/${result.support_touches}`} />
                        <Metric label="Prev trend" value={result.prev_trend} />
                        <Metric label="Trend alignment" value={result.trend_alignment} />
                        <Metric label="Squeeze" value={String(result.squeeze_score)} />
                        <Metric label="1h turnover" value={formatUsd(result.turnover_1h_usd)} />
                        <Metric label="Flat range" value={`${formatNumber(result.flat_range_pct, 2)}%`} />
                        <Metric label="R2" value={formatNumber(result.flat_r_squared, 3)} />
                        <Metric label="ADX" value={formatNumber(result.adx_14, 1)} />
                        <Metric label="Slope" value={formatNumber(result.flat_slope_rel, 5)} />
                        <Metric label="Inside close/body" value={`${formatNumber(result.close_inside_ratio, 2)} / ${formatNumber(result.body_inside_ratio, 2)}`} />
                        <Metric label="False breakouts" value={String(result.false_breakouts)} />
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
                <td colSpan={10} className="empty-state">
                  {data ? "Setup не найдены с текущими фильтрами." : "Результаты появятся здесь после сканирования."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
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

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);

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
  chart_candles: ChartCandle[];
  range_start_timestamp: number;
  range_end_timestamp: number;
  trend_start_timestamp: number;
  trend_end_timestamp: number;
  reasons: string[];
  warnings: string[];
};

type ChartCandle = {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
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
  const [turnoverMin, setTurnoverMin] = React.useState(2_000_000);
  const [expandedTicker, setExpandedTicker] = React.useState<string | null>(null);
  const [chartTicker, setChartTicker] = React.useState<string | null>(null);

  async function runScan(force = false) {
    setLoading(true);
    setError(null);
    setExpandedTicker(null);
    setChartTicker(null);
    try {
      const response = await fetch("/api/scan", {
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
          Минимальный скоринг
          <input type="number" min="0" max="100" value={minRating} onChange={(event) => setMinRating(Number(event.target.value))} />
        </label>
        <label>
          24ч Объем
          <input type="number" min="0" step="100000" value={turnoverMin} onChange={(event) => setTurnoverMin(Number(event.target.value))} />
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
                    <td colSpan={11}>
                      <SetupChart result={result} />
                    </td>
                  </tr>
                )}
                {expandedTicker === result.ticker && (
                  <tr className="details-row">
                    <td colSpan={11}>
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
                <td colSpan={11} className="empty-state">
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

function SetupChart({ result }: { result: ScanResult }) {
  const candles = result.chart_candles;
  if (!candles.length) {
    return <div className="chart-fallback">Нет свечей для встроенного графика.</div>;
  }

  const width = 1080;
  const height = 360;
  const pad = { top: 22, right: 64, bottom: 34, left: 54 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const minLow = Math.min(...candles.map((candle) => candle.low), result.support_level);
  const maxHigh = Math.max(...candles.map((candle) => candle.high), result.resistance_level);
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

  return (
    <div className="chart-panel">
      <div className="chart-header">
        <div>
          <strong>{result.ticker}</strong>
          <span>{result.direction} · {result.prev_trend} · {result.trend_alignment}</span>
        </div>
        <span className={`flat-badge ${result.sideways_quality}`}>{result.sideways_quality} {result.sideways_confidence}</span>
      </div>
      <svg className="setup-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Свой график ${result.ticker}`}>
        <rect x={0} y={0} width={width} height={height} rx={8} fill="#11161f" />
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = pad.top + plotHeight * ratio;
          return <line key={ratio} x1={pad.left} x2={width - pad.right} y1={y} y2={y} className="grid-line" />;
        })}
        <rect x={trendX} y={pad.top} width={trendW} height={plotHeight} className="trend-zone" />
        <rect x={rangeX} y={rangeY} width={rangeW} height={rangeH} className="range-zone" />
        <line x1={pad.left} x2={width - pad.right} y1={resistanceY} y2={resistanceY} className="resistance-line" />
        <line x1={pad.left} x2={width - pad.right} y1={supportY} y2={supportY} className="support-line" />
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
      <div className="chart-diagnostics">
        <Metric label="R2" value={formatNumber(result.flat_r_squared, 3)} />
        <Metric label="ADX" value={formatNumber(result.adx_14, 1)} />
        <Metric label="Slope" value={formatNumber(result.flat_slope_rel, 5)} />
        <Metric label="Inside close/body" value={`${formatNumber(result.close_inside_ratio, 2)} / ${formatNumber(result.body_inside_ratio, 2)}`} />
        <Metric label="False breakouts" value={String(result.false_breakouts)} />
        <Metric label="Range candles" value={String(result.range_candles)} />
      </div>
      <div className="reason-columns">
        <ListBlock title="Reasons" items={result.reasons} />
        <ListBlock title="Warnings" items={result.warnings.length ? result.warnings : ["no warnings"]} />
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

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);

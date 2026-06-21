from datetime import datetime, timedelta, timezone
from io import BytesIO
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.database import Base, DetectedSetup, MLSignalSnapshot, RangeEpisode, ScanRun, SetupObservation, TradePlanVariant
from backend.app.history import export_history_xlsx, query_history
from backend.app.ml_export import export_training_parquet
from backend.app.ml_pipeline import persist_ml_snapshots
from backend.app.models import Candle, ScanResponse, ScanResult
from backend.app.outcomes import evaluate_outcome
from backend.app.persistence import persist_scan
from backend.app.reset_history import reset_history, table_counts
from backend.app.worker import current_schedule_slot, next_schedule_slot


def minute_candle(index: int, *, high: float, low: float, close: float) -> Candle:
    return Candle(
        timestamp=index * 60_000,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=100,
        turnover=10_000,
    )


def scan_result(**overrides) -> ScanResult:
    payload = {
        "ticker": "AAAUSDT",
        "bybit_url": "https://www.bybit.com/trade/usdt/AAAUSDT",
        "price": 100.8,
        "change_1h_pct": 1.0,
        "turnover_24h_usd": 3_000_000,
        "turnover_1h_usd": 100_000,
        "rating": 80,
        "class": "A",
        "setup_status": "breakout_watch",
        "direction": "LONG",
        "direction_candidate": "LONG",
        "direction_confirmation": "confirmed",
        "btc_correlation_5h": 0.5,
        "btc_correlation_pairs": 60,
        "btc_change_pct_5h": 1,
        "asset_change_pct_5h": 2,
        "relative_strength_pct": 1,
        "btc_trend": "bullish",
        "btc_signal": "btc_confirmed",
        "btc_score_adjustment": 3,
        "rating_with_btc_preview": 83,
        "range_candles": 3,
        "range_minutes": 15,
        "range_width_pct": 2,
        "resistance_level": 101,
        "support_level": 99,
        "price_position": 0.9,
        "resistance_touches": 3,
        "support_touches": 2,
        "false_breakouts": 0,
        "volume_ratio": 1.4,
        "range_turnover_avg": 10_000,
        "previous_turnover_avg": 8_000,
        "prev_trend": "bullish",
        "squeeze_score": 70,
        "sideways_confidence": 85,
        "sideways_quality": "strong",
        "flat_range_pct": 1,
        "flat_slope_rel": 0.0001,
        "flat_r_squared": 0.1,
        "adx_14": 18,
        "close_inside_ratio": 0.9,
        "body_inside_ratio": 0.8,
        "trend_alignment": "aligned",
        "chart_candles": [
            {
                "timestamp": 300_000,
                "open": 100.5,
                "high": 101,
                "low": 100.1,
                "close": 100.8,
                "volume": 100,
                "turnover": 10_000,
            },
            {
                "timestamp": 600_000,
                "open": 100.7,
                "high": 101,
                "low": 100.2,
                "close": 100.9,
                "volume": 110,
                "turnover": 11_000,
            },
            {
                "timestamp": 900_000,
                "open": 100.8,
                "high": 101,
                "low": 100.3,
                "close": 100.9,
                "volume": 120,
                "turnover": 12_000,
            },
        ],
        "range_start_timestamp": 300_000,
        "range_end_timestamp": 900_000,
        "trend_start_timestamp": 0,
        "trend_end_timestamp": 0,
        "trade_plan_status": "READY",
        "trade_plan_version": "wick-shelf-v1",
        "entry_price": 101,
        "stop_loss": 100.08,
        "take_profit": 103.76,
        "risk_price": 0.92,
        "reward_risk": 3,
        "shelf_start_timestamp": 300_000,
        "shelf_end_timestamp": 900_000,
        "trade_plan_variants": [
            {
                "version": "wick-shelf-v1",
                "status": "READY",
                "reason": None,
                "direction": "LONG",
                "activation": "boundary_touch",
                "entry_price": 101,
                "stop_loss": 100.08,
                "risk_price": 0.92,
                "target_1r": 101.92,
                "target_2r": 102.84,
                "target_3r": 103.76,
                "trigger_price": 101,
            },
            {
                "version": "breakout-buffer-v2",
                "status": "READY",
                "reason": None,
                "direction": "LONG",
                "activation": "price_crosses_buffer",
                "entry_price": 101,
                "stop_loss": 100.08,
                "risk_price": 0.92,
                "target_1r": 101.92,
                "target_2r": 102.84,
                "target_3r": 103.76,
                "trigger_price": 101,
            },
        ],
        "reasons": [],
        "warnings": [],
    }
    payload.update(overrides)
    return ScanResult.model_validate(payload)


def scan_response(scan_time: datetime, result: ScanResult) -> ScanResponse:
    return ScanResponse(
        scan_time=scan_time.isoformat(),
        scan_duration_ms=100,
        total_symbols=1,
        filtered_symbols=1,
        analyzed_symbols=1,
        symbols_with_errors=0,
        signals_found=1,
        from_cache=False,
        results=[result],
    )


def test_outcome_statuses_and_conservative_same_candle_rule() -> None:
    deadline = datetime(2026, 6, 15, 13, tzinfo=timezone.utc)

    no_trade = evaluate_outcome(
        direction="LONG",
        entry_price=101,
        stop_loss=100,
        take_profit=104,
        risk_price=1,
        candles=[minute_candle(0, high=100.9, low=100.2, close=100.5)],
        deadline=deadline,
    )
    pending = evaluate_outcome(
        direction="LONG",
        entry_price=101,
        stop_loss=100,
        take_profit=104,
        risk_price=1,
        candles=[minute_candle(0, high=101.2, low=100.8, close=101.1)],
        deadline=deadline,
    )
    take = evaluate_outcome(
        direction="LONG",
        entry_price=101,
        stop_loss=100,
        take_profit=104,
        risk_price=1,
        candles=[
            minute_candle(0, high=101.2, low=100.8, close=101.1),
            minute_candle(1, high=104.1, low=101, close=104),
        ],
        deadline=deadline,
    )
    ambiguous = evaluate_outcome(
        direction="LONG",
        entry_price=101,
        stop_loss=100,
        take_profit=104,
        risk_price=1,
        candles=[minute_candle(0, high=104.1, low=99.9, close=102)],
        deadline=deadline,
    )

    assert no_trade.outcome == "NO_TRADE"
    assert pending.outcome == "PENDING"
    assert take.outcome == "TAKE"
    assert take.mfe_r == pytest.approx(3.1)
    assert ambiguous.outcome == "STOP"
    assert ambiguous.ambiguous_intrabar is True


def test_persistence_deduplicates_symbol_inside_sixty_minutes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    second_time = first_time + timedelta(minutes=45)

    with Session(engine) as session:
        persist_scan(session, scan_response(first_time, scan_result()), first_time)
        session.commit()
        repeated = scan_result(
            direction="SHORT",
            direction_candidate="SHORT",
            support_level=99.05,
            resistance_level=101.05,
            range_start_timestamp=360_000,
            range_end_timestamp=960_000,
            trade_plan_variants=[
                {
                    "version": "breakout-buffer-v2",
                    "status": "INVALID",
                    "reason": "adaptive stop is too deep",
                    "direction": "SHORT",
                    "activation": "price_crosses_buffer",
                    "entry_price": 99,
                }
            ],
        )
        persist_scan(session, scan_response(second_time, repeated), second_time)
        session.commit()

        setups = session.scalars(select(DetectedSetup).order_by(DetectedSetup.first_seen_at)).all()
        observations = session.scalars(select(SetupObservation)).all()

    assert len(setups) == 1
    assert len(observations) == 1
    assert setups[0].direction == "LONG"
    assert setups[0].support_level == 99
    assert setups[0].resistance_level == 101
    assert setups[0].last_seen_at.replace(tzinfo=timezone.utc) == first_time
    assert setups[0].outcome == "PENDING"
    assert setups[0].entry_price == 101


def test_persistence_allows_same_symbol_again_after_sixty_minutes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    second_time = first_time + timedelta(minutes=60)

    with Session(engine) as session:
        persist_scan(session, scan_response(first_time, scan_result()), first_time)
        session.commit()
        persist_scan(session, scan_response(second_time, scan_result()), second_time)
        session.commit()

        setups = session.scalars(select(DetectedSetup).order_by(DetectedSetup.first_seen_at)).all()
        observations = session.scalars(select(SetupObservation)).all()

    assert len(setups) == 2
    assert len(observations) == 2
    assert setups[0].first_seen_at.replace(tzinfo=timezone.utc) == first_time
    assert setups[1].first_seen_at.replace(tzinfo=timezone.utc) == second_time


def test_repeated_signal_keeps_single_history_record_but_adds_fifteen_minute_ml_snapshot() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    second_time = first_time + timedelta(minutes=15)
    result = scan_result()

    with Session(engine) as session:
        first_run = persist_scan(session, scan_response(first_time, result), first_time)
        assert persist_ml_snapshots(session, first_run, [], [result]) == 1
        session.commit()

        second_run = persist_scan(session, scan_response(second_time, result), second_time)
        assert persist_ml_snapshots(session, second_run, [], [result]) == 1
        assert persist_ml_snapshots(session, second_run, [], [result]) == 0
        session.commit()

        setups = session.scalars(select(DetectedSetup).order_by(DetectedSetup.first_seen_at)).all()
        observations = session.scalars(select(SetupObservation)).all()
        snapshots = session.scalars(select(MLSignalSnapshot).order_by(MLSignalSnapshot.observed_at)).all()

    assert len(setups) == 1
    assert len(observations) == 1
    assert len(snapshots) == 2
    assert snapshots[0].setup_id == snapshots[1].setup_id == setups[0].id


def test_low_scoring_v2_candidate_is_saved_to_history() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    scan_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)

    with Session(engine) as session:
        persist_scan(session, scan_response(scan_time, scan_result(rating=42, **{"class": "Weak"})), scan_time)
        session.commit()
        history = query_history(session, min_rating=0)

    assert history.total == 1
    assert history.items[0].rating == 42
    assert history.items[0].setup_class == "Weak"


def test_history_uses_breakout_buffer_v2_as_canonical_plan() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    scan_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    result = scan_result(
        trade_plan_status="READY",
        trade_plan_version="wick-shelf-v1",
        entry_price=101,
        stop_loss=100,
        take_profit=104,
        risk_price=1,
        trade_plan_variants=[
            {
                "version": "wick-shelf-v1",
                "status": "READY",
                "reason": None,
                "direction": "LONG",
                "activation": "boundary_touch",
                "entry_price": 101,
                "stop_loss": 100,
                "risk_price": 1,
                "target_1r": 102,
                "target_2r": 103,
                "target_3r": 104,
                "trigger_price": 101,
            },
            {
                "version": "breakout-buffer-v2",
                "status": "READY",
                "reason": None,
                "direction": "LONG",
                "activation": "price_crosses_buffer",
                "entry_price": 102,
                "stop_loss": 101,
                "risk_price": 1,
                "target_1r": 103,
                "target_2r": 104,
                "target_3r": 105,
                "trigger_price": 102,
            },
        ],
    )

    with Session(engine) as session:
        persist_scan(session, scan_response(scan_time, result), scan_time)
        session.commit()
        setup = session.scalar(select(DetectedSetup))

    assert setup is not None
    assert setup.trade_plan_version == "breakout-buffer-v2"
    assert setup.entry_price == 102
    assert setup.stop_loss == 101
    assert setup.take_profit == 105
    assert setup.outcome == "PENDING"


def test_v2_parquet_exports_invalid_and_no_trade_setups() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    second_time = first_time + timedelta(minutes=15)
    ready = scan_result()
    invalid = scan_result(
        ticker="BBBUSDT",
        bybit_url="https://www.bybit.com/trade/usdt/BBBUSDT",
        rating=35,
        **{"class": "Weak"},
        trade_plan_variants=[
            {
                "version": "breakout-buffer-v2",
                "status": "INVALID",
                "reason": "adaptive stop is too deep",
                "direction": "LONG",
                "activation": "price_crosses_buffer",
                "entry_price": 101,
            }
        ],
    )

    with Session(engine) as session:
        first_run = persist_scan(session, scan_response(first_time, ready), first_time)
        assert persist_ml_snapshots(session, first_run, [], [ready]) == 1
        setup = session.scalar(select(DetectedSetup).where(DetectedSetup.symbol == "AAAUSDT"))
        assert setup is not None
        setup.outcome = "NO_TRADE"
        setup.resolved_at = first_time + timedelta(hours=1)

        second_run = persist_scan(session, scan_response(second_time, invalid), second_time)
        assert persist_ml_snapshots(session, second_run, [], [invalid]) == 1
        session.commit()

        table = pq.read_table(BytesIO(export_training_parquet(session)))
        rows = sorted(table.to_pylist(), key=lambda row: row["symbol"])

    assert [row["symbol"] for row in rows] == ["AAAUSDT", "BBBUSDT"]
    assert rows[0]["outcome"] == "NO_TRADE"
    assert rows[0]["plan_version"] == "breakout-buffer-v2"
    assert rows[1]["plan_status"] == "INVALID"
    assert rows[1]["outcome"] == "NOT_APPLICABLE"
    assert rows[1]["rating"] == 35


def test_v2_parquet_uses_deduplicated_history_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    second_time = first_time + timedelta(minutes=15)
    result = scan_result()

    with Session(engine) as session:
        first_run = persist_scan(session, scan_response(first_time, result), first_time)
        assert persist_ml_snapshots(session, first_run, [], [result]) == 1
        second_run = persist_scan(session, scan_response(second_time, result), second_time)
        assert persist_ml_snapshots(session, second_run, [], [result]) == 1
        session.commit()

        table = pq.read_table(BytesIO(export_training_parquet(session)))
        rows = table.to_pylist()

    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["setup_id"] is not None


def test_reset_history_migration_clears_working_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    scan_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "0005_reset_history_for_v2.py"
    spec = spec_from_file_location("reset_history_for_v2", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    with Session(engine) as session:
        run = persist_scan(session, scan_response(scan_time, scan_result()), scan_time)
        assert persist_ml_snapshots(session, run, [], [scan_result()]) == 1
        session.commit()

    with engine.begin() as connection:
        migration.reset_history_tables(connection)

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ScanRun)) == 0
        assert session.scalar(select(func.count()).select_from(DetectedSetup)) == 0
        assert session.scalar(select(func.count()).select_from(SetupObservation)) == 0
        assert session.scalar(select(func.count()).select_from(RangeEpisode)) == 0
        assert session.scalar(select(func.count()).select_from(MLSignalSnapshot)) == 0
        assert session.scalar(select(func.count()).select_from(TradePlanVariant)) == 0


def test_reset_history_command_clears_working_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    scan_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)

    with Session(engine) as session:
        run = persist_scan(session, scan_response(scan_time, scan_result()), scan_time)
        assert persist_ml_snapshots(session, run, [], [scan_result()]) == 1
        session.commit()

    with engine.begin() as connection:
        before = table_counts(connection)
        reset_history(connection)
        after = table_counts(connection)

    assert before["detected_setups"] == 1
    assert before["ml_signal_snapshots"] == 1
    assert all(count == 0 for count in after.values())


def test_history_query_and_xlsx_export_use_persisted_setup() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    scan_time = datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)

    with Session(engine) as session:
        persist_scan(session, scan_response(scan_time, scan_result()), scan_time)
        session.commit()
        history = query_history(session, symbol="AAA", direction="LONG", min_rating=75)
        content = export_history_xlsx(history)

    workbook = load_workbook(BytesIO(content), read_only=True)
    sheet = workbook["История"]

    assert history.total == 1
    assert history.items[0].entry_price == 101
    assert sheet["B2"].value == "AAAUSDT"
    assert sheet["O2"].value == "PENDING"


def test_worker_schedule_runs_every_fifteen_minutes_from_minute_two_utc() -> None:
    before = datetime(2026, 6, 15, 12, 1, 30, tzinfo=timezone.utc)
    after = datetime(2026, 6, 15, 12, 2, 30, tzinfo=timezone.utc)
    later = datetime(2026, 6, 15, 12, 31, 30, tzinfo=timezone.utc)

    assert current_schedule_slot(before) == datetime(2026, 6, 15, 11, 47, tzinfo=timezone.utc)
    assert current_schedule_slot(after) == datetime(2026, 6, 15, 12, 2, tzinfo=timezone.utc)
    assert current_schedule_slot(later) == datetime(2026, 6, 15, 12, 17, tzinfo=timezone.utc)
    assert next_schedule_slot(after) == datetime(2026, 6, 15, 12, 17, tzinfo=timezone.utc)

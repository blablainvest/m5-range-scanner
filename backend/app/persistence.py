from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import config
from .database import DetectedSetup, ScanRun, SetupObservation
from .models import ScanResponse, ScanResult, TradePlanView


CANONICAL_TRADE_PLAN_VERSION = "breakout-buffer-v2"


def timestamp_to_datetime(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def parse_scan_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def interval_overlap_ratio(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> float:
    start_a, end_a, start_b, end_b = map(ensure_utc, (start_a, end_a, start_b, end_b))
    intersection = max(0.0, (min(end_a, end_b) - max(start_a, start_b)).total_seconds())
    shortest = min((end_a - start_a).total_seconds(), (end_b - start_b).total_seconds())
    return intersection / shortest if shortest > 0 else 0.0


def price_overlap_ratio(support_a: float, resistance_a: float, support_b: float, resistance_b: float) -> float:
    intersection = max(0.0, min(resistance_a, resistance_b) - max(support_a, support_b))
    shortest = min(resistance_a - support_a, resistance_b - support_b)
    return intersection / shortest if shortest > 0 else 0.0


def _find_matching_setup(
    session: Session,
    result: ScanResult,
    observed_at: datetime,
) -> Optional[DetectedSetup]:
    dedup_since = observed_at - timedelta(minutes=config.setup_dedup_minutes)
    return session.scalar(
        select(DetectedSetup)
        .where(
            DetectedSetup.symbol == result.ticker,
            DetectedSetup.first_seen_at > dedup_since,
        )
        .order_by(DetectedSetup.first_seen_at.desc())
        .limit(1)
    )


def _canonical_trade_plan(result: ScanResult) -> Optional[TradePlanView]:
    return next(
        (plan for plan in result.trade_plan_variants if plan.version == CANONICAL_TRADE_PLAN_VERSION),
        None,
    )


def _reward_risk(plan: TradePlanView) -> Optional[float]:
    if plan.entry_price is None or plan.target_3r is None or plan.risk_price is None or plan.risk_price <= 0:
        return None
    return abs(plan.target_3r - plan.entry_price) / plan.risk_price


def _apply_trade_plan(setup: DetectedSetup, result: ScanResult, observed_at: datetime) -> None:
    plan = _canonical_trade_plan(result)
    if plan is None:
        if setup.trade_plan_status == "READY" or result.trade_plan_status != "READY":
            return
        setup.direction = result.direction
        setup.trade_plan_status = result.trade_plan_status
        setup.trade_plan_reason = result.trade_plan_reason
        setup.trade_plan_version = result.trade_plan_version
        setup.trade_plan_created_at = observed_at
        setup.outcome_deadline_at = observed_at + timedelta(minutes=config.outcome_window_minutes)
        setup.entry_price = result.entry_price
        setup.stop_loss = result.stop_loss
        setup.take_profit = result.take_profit
        setup.risk_price = result.risk_price
        setup.reward_risk = result.reward_risk
        setup.shelf_start_at = (
            timestamp_to_datetime(result.shelf_start_timestamp) if result.shelf_start_timestamp is not None else None
        )
        setup.shelf_end_at = (
            timestamp_to_datetime(result.shelf_end_timestamp) if result.shelf_end_timestamp is not None else None
        )
        setup.outcome = "PENDING"
        return

    setup.direction = result.direction
    setup.trade_plan_status = plan.status
    setup.trade_plan_reason = plan.reason
    setup.trade_plan_version = plan.version
    setup.entry_price = plan.entry_price
    setup.stop_loss = plan.stop_loss
    setup.take_profit = plan.target_3r
    setup.risk_price = plan.risk_price
    setup.reward_risk = _reward_risk(plan)
    setup.shelf_start_at = None
    setup.shelf_end_at = None
    if plan.status == "READY":
        setup.trade_plan_created_at = observed_at
        setup.outcome_deadline_at = observed_at + timedelta(minutes=config.outcome_window_minutes)
        setup.outcome = "PENDING"
    else:
        setup.trade_plan_created_at = None
        setup.outcome_deadline_at = None
        setup.outcome = "NOT_APPLICABLE"


def persist_scan(session: Session, response: ScanResponse, scheduled_at: datetime) -> ScanRun:
    observed_at = parse_scan_time(response.scan_time)
    existing = session.scalar(select(ScanRun).where(ScanRun.scheduled_at == scheduled_at))
    if existing is not None and existing.status == "COMPLETED":
        return existing

    if existing is None:
        run = ScanRun(scheduled_at=scheduled_at, started_at=observed_at)
        session.add(run)
        session.flush()
    else:
        run = existing
    run.started_at = observed_at
    run.completed_at = observed_at
    run.status = "COMPLETED"
    run.scan_duration_ms = response.scan_duration_ms
    run.total_symbols = response.total_symbols
    run.analyzed_symbols = response.analyzed_symbols
    run.symbols_with_errors = response.symbols_with_errors
    run.signals_found = response.signals_found
    run.error = None

    seen_setup_ids: set[int] = set()
    for result in response.results:
        setup = _find_matching_setup(session, result, observed_at)
        if setup is not None:
            seen_setup_ids.add(setup.id)
            continue

        setup = DetectedSetup(
            symbol=result.ticker,
            direction=result.direction,
            active=True,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            range_start_at=timestamp_to_datetime(result.range_start_timestamp),
            range_end_at=timestamp_to_datetime(result.range_end_timestamp),
            support_level=result.support_level,
            resistance_level=result.resistance_level,
            trade_plan_status="NOT_APPLICABLE",
            trade_plan_reason=result.trade_plan_reason,
            trade_plan_version=result.trade_plan_version,
            outcome="NOT_APPLICABLE",
        )
        session.add(setup)
        session.flush()

        _apply_trade_plan(setup, result, observed_at)
        if _canonical_trade_plan(result) is None and result.trade_plan_status != "READY" and setup.trade_plan_status != "READY":
            setup.trade_plan_status = result.trade_plan_status
            setup.trade_plan_reason = result.trade_plan_reason

        range_candles = [
            candle.model_dump()
            for candle in result.chart_candles
            if result.range_start_timestamp <= candle.timestamp <= result.range_end_timestamp
        ]
        session.add(
            SetupObservation(
                setup_id=setup.id,
                scan_run_id=run.id,
                observed_at=observed_at,
                rating=result.rating,
                setup_class=result.setup_class,
                direction=result.direction,
                result_json=result.model_dump(by_alias=True),
                range_candles_json=range_candles,
            )
        )
        seen_setup_ids.add(setup.id)

    active_setups = session.scalars(select(DetectedSetup).where(DetectedSetup.active.is_(True))).all()
    for setup in active_setups:
        if setup.id not in seen_setup_ids:
            setup.missed_scans += 1
            if setup.missed_scans >= 2:
                setup.active = False

    return run

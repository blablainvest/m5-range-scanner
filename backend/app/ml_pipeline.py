from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .bybit_client import BybitClient
from .database import (
    BreakoutLabel,
    DetectedSetup,
    MarketCandle,
    MLSignalSnapshot,
    RangeEpisode,
    ScanRun,
    SetupObservation,
    TradePlanResult,
    TradePlanVariant,
)
from .detector_v2 import DETECTOR_VERSION as V2_DETECTOR_VERSION
from .models import Candle, ScanResult, TradePlanView
from .persistence import ensure_utc, timestamp_to_datetime
from .trade_plan import breakout_buffer, build_trade_plan_variants


logger = logging.getLogger(__name__)
FEATURE_SCHEMA_VERSION = "ml-features-v1"
HORIZONS = (15, 30, 60, 120, 240)
PLAN_HORIZONS = (60, 240)


def _overlap_ratio(low_a: float, high_a: float, low_b: float, high_b: float) -> float:
    intersection = max(0.0, min(high_a, high_b) - max(low_a, low_b))
    shortest = min(high_a - low_a, high_b - low_b)
    return intersection / shortest if shortest > 0 else 0.0


def _find_or_create_episode(
    session: Session,
    result: ScanResult,
    detector_version: str,
    observed_at: datetime,
) -> RangeEpisode:
    candidates = session.scalars(
        select(RangeEpisode)
        .where(
            RangeEpisode.detector_version == detector_version,
            RangeEpisode.symbol == result.ticker,
            RangeEpisode.ended_at.is_(None),
        )
        .order_by(RangeEpisode.last_snapshot_at.desc())
        .limit(5)
    ).all()
    for episode in candidates:
        if _overlap_ratio(
            episode.support_level,
            episode.resistance_level,
            result.support_level,
            result.resistance_level,
        ) >= 0.7:
            episode.last_snapshot_at = observed_at
            return episode
    episode = RangeEpisode(
        detector_version=detector_version,
        symbol=result.ticker,
        direction=result.direction,
        started_at=timestamp_to_datetime(result.range_start_timestamp),
        first_snapshot_at=observed_at,
        last_snapshot_at=observed_at,
        support_level=result.support_level,
        resistance_level=result.resistance_level,
    )
    session.add(episode)
    session.flush()
    return episode


def _setup_for_result(session: Session, result: ScanResult, observed_at: datetime) -> Optional[DetectedSetup]:
    return session.scalar(
        select(DetectedSetup)
        .where(
            DetectedSetup.symbol == result.ticker,
            DetectedSetup.first_seen_at <= observed_at,
            DetectedSetup.first_seen_at > observed_at - timedelta(minutes=60),
        )
        .order_by(DetectedSetup.first_seen_at.desc())
        .limit(1)
    )


def _store_candles(
    session: Session,
    symbol: str,
    interval: str,
    candles: Iterable[Candle],
) -> None:
    for candle in candles:
        timestamp = timestamp_to_datetime(candle.timestamp)
        existing = session.scalar(
            select(MarketCandle.id).where(
                MarketCandle.symbol == symbol,
                MarketCandle.interval == interval,
                MarketCandle.timestamp == timestamp,
            )
        )
        if existing is not None:
            continue
        session.add(
            MarketCandle(
                symbol=symbol,
                interval=interval,
                timestamp=timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                turnover=candle.turnover,
            )
        )


def _plans_for_result(result: ScanResult) -> list[TradePlanView]:
    if result.trade_plan_variants:
        return result.trade_plan_variants
    candles = [Candle.model_validate(item.model_dump()) for item in result.chart_candles]
    range_candles = [
        candle
        for candle in candles
        if result.range_start_timestamp <= candle.timestamp <= result.range_end_timestamp
    ]
    return build_trade_plan_variants(
        direction=result.direction,
        support=result.support_level,
        resistance=result.resistance_level,
        current_price=result.price,
        tick_size=result.tick_size or 1e-12,
        range_candles=range_candles,
        context_candles=candles,
    )


def persist_ml_snapshots(
    session: Session,
    run: ScanRun,
    primary_results: list[ScanResult],
    background_results: list[ScanResult],
) -> int:
    observed_at = ensure_utc(run.started_at)
    created = 0
    groups = (("v1", primary_results), (V2_DETECTOR_VERSION, background_results))
    for detector_version, results in groups:
        for result in results:
            existing = session.scalar(
                select(MLSignalSnapshot.id).where(
                    MLSignalSnapshot.detector_version == detector_version,
                    MLSignalSnapshot.symbol == result.ticker,
                    MLSignalSnapshot.observed_at == observed_at,
                )
            )
            if existing is not None:
                continue
            episode = _find_or_create_episode(session, result, detector_version, observed_at)
            setup = _setup_for_result(session, result, observed_at)
            buffer_price = breakout_buffer(result.tick_size or 1e-12, result.atr_14)
            snapshot = MLSignalSnapshot(
                episode_id=episode.id,
                setup_id=setup.id if setup is not None else None,
                scan_run_id=run.id,
                detector_version=detector_version,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                symbol=result.ticker,
                observed_at=observed_at,
                rating=result.rating,
                direction=result.direction,
                range_start_at=timestamp_to_datetime(result.range_start_timestamp),
                range_end_at=timestamp_to_datetime(result.range_end_timestamp),
                support_level=result.support_level,
                resistance_level=result.resistance_level,
                tick_size=result.tick_size or 1e-12,
                atr_14=result.atr_14,
                breakout_buffer=buffer_price,
                range_age_minutes=result.range_minutes,
                funding_rate=result.funding_rate,
                open_interest=result.open_interest,
                open_interest_value=result.open_interest_value,
                features_json=result.model_dump(by_alias=True),
            )
            session.add(snapshot)
            session.flush()
            for plan in _plans_for_result(result):
                session.add(
                    TradePlanVariant(
                        snapshot_id=snapshot.id,
                        plan_version=plan.version,
                        status=plan.status,
                        reason=plan.reason,
                        direction=plan.direction,
                        activation=plan.activation,
                        entry_price=plan.entry_price,
                        stop_loss=plan.stop_loss,
                        risk_price=plan.risk_price,
                        target_1r=plan.target_1r,
                        target_2r=plan.target_2r,
                        target_3r=plan.target_3r,
                        trigger_price=plan.trigger_price,
                        retest_zone_low=plan.retest_zone_low,
                        retest_zone_high=plan.retest_zone_high,
                        parameters_json=plan.model_dump(),
                    )
                )
            _store_candles(
                session,
                result.ticker,
                "5",
                [
                    Candle.model_validate(candle.model_dump())
                    for candle in (result.ml_candles or result.chart_candles)
                ],
            )
            created += 1
    return created


def backfill_v1_snapshots(session: Session) -> int:
    observations = session.scalars(
        select(SetupObservation)
        .where(SetupObservation.rating >= 70)
        .order_by(SetupObservation.observed_at)
    ).all()
    created = 0
    for observation in observations:
        run = observation.scan_run or session.get(ScanRun, observation.scan_run_id)
        if run is None:
            continue
        result = ScanResult.model_validate(observation.result_json)
        created += persist_ml_snapshots(session, run, [result], [])
    return created


@dataclass(frozen=True)
class BreakoutEvaluation:
    wick_breakout: bool
    close_breakout: bool
    confirmed_breakout: bool
    false_breakout: bool
    breakout_direction: Optional[str]
    first_breakout_at: Optional[datetime]


def evaluate_breakout(
    *,
    support: float,
    resistance: float,
    buffer_price: float,
    candles: list[Candle],
) -> BreakoutEvaluation:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    wick = False
    close_breakout = False
    confirmed = False
    false_breakout = False
    direction: Optional[str] = None
    first_at: Optional[datetime] = None
    outside_streak = 0
    close_direction: Optional[str] = None
    close_index: Optional[int] = None
    for index, candle in enumerate(ordered):
        if candle.high > resistance or candle.low < support:
            wick = True
        current_direction: Optional[str] = None
        if candle.close > resistance + buffer_price:
            current_direction = "LONG"
        elif candle.close < support - buffer_price:
            current_direction = "SHORT"
        if current_direction is None:
            outside_streak = 0
            close_direction = None
            continue
        if not close_breakout:
            close_breakout = True
            direction = current_direction
            first_at = timestamp_to_datetime(candle.timestamp)
            close_index = index
        if current_direction == close_direction:
            outside_streak += 1
        else:
            close_direction = current_direction
            outside_streak = 1
        if outside_streak >= 2:
            confirmed = True
    if close_index is not None:
        later = ordered[close_index + 1 : min(len(ordered), close_index + 4)]
        false_breakout = any(support <= item.close <= resistance for item in later)
    return BreakoutEvaluation(wick, close_breakout, confirmed, false_breakout, direction, first_at)


@dataclass(frozen=True)
class PlanEvaluation:
    outcome: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_1r: Optional[float]
    target_2r: Optional[float]
    target_3r: Optional[float]
    entered_at: Optional[datetime]
    stopped_at: Optional[datetime]
    hit_1r_at: Optional[datetime]
    hit_2r_at: Optional[datetime]
    hit_3r_at: Optional[datetime]
    mfe_r: Optional[float]
    mae_r: Optional[float]
    ambiguous_intrabar: bool


def _v3_entry(
    plan: TradePlanVariant,
    m5_candles: list[Candle],
) -> Optional[tuple[datetime, float, float, float, float, float]]:
    if plan.trigger_price is None or plan.retest_zone_low is None or plan.retest_zone_high is None:
        return None
    streak = 0
    confirmation_index: Optional[int] = None
    for index, candle in enumerate(sorted(m5_candles, key=lambda item: item.timestamp)):
        beyond = (
            candle.close >= plan.trigger_price
            if plan.direction == "LONG"
            else candle.close <= plan.trigger_price
        )
        streak = streak + 1 if beyond else 0
        if streak >= 2:
            confirmation_index = index
            break
    if confirmation_index is None:
        return None
    ordered = sorted(m5_candles, key=lambda item: item.timestamp)
    for candle in ordered[confirmation_index + 1 : confirmation_index + 4]:
        if candle.low <= plan.retest_zone_high and candle.high >= plan.retest_zone_low:
            entry = plan.entry_price
            retest_buffer = max((plan.retest_zone_high - plan.retest_zone_low) / 2, abs(entry) * 1e-8)
            stop = candle.low - retest_buffer if plan.direction == "LONG" else candle.high + retest_buffer
            risk = entry - stop if plan.direction == "LONG" else stop - entry
            if risk <= 0:
                return None
            if plan.direction == "LONG":
                targets = (entry + risk, entry + risk * 2, entry + risk * 3)
            else:
                targets = (entry - risk, entry - risk * 2, entry - risk * 3)
            return timestamp_to_datetime(candle.timestamp), entry, stop, *targets
    return None


def evaluate_plan(
    plan: TradePlanVariant,
    m1_candles: list[Candle],
    m5_candles: list[Candle],
) -> PlanEvaluation:
    if (
        plan.entry_price is None
        or plan.stop_loss is None
        or plan.risk_price is None
        or plan.risk_price <= 0
    ):
        return PlanEvaluation(
            "NOT_APPLICABLE", None, None, None, None, None, None, None, None, None, None, None, None, False
        )
    v3 = _v3_entry(plan, m5_candles) if plan.activation == "two_m5_closes_then_retest" else None
    if plan.activation == "two_m5_closes_then_retest" and v3 is None:
        return PlanEvaluation("NO_TRADE", None, None, None, None, None, None, None, None, None, None, None, None, False)
    forced_entry = v3[0] if v3 is not None else None
    entry_price = v3[1] if v3 is not None else plan.entry_price
    stop_loss = v3[2] if v3 is not None else plan.stop_loss
    target_1r = v3[3] if v3 is not None else plan.target_1r
    target_2r = v3[4] if v3 is not None else plan.target_2r
    target_3r = v3[5] if v3 is not None else plan.target_3r
    risk_price = (
        entry_price - stop_loss if plan.direction == "LONG" else stop_loss - entry_price
    )
    entered_at: Optional[datetime] = forced_entry
    hit_1r = hit_2r = hit_3r = stopped_at = None
    max_favorable = max_adverse = 0.0
    ambiguous = False
    for candle in sorted(m1_candles, key=lambda item: item.timestamp):
        candle_at = timestamp_to_datetime(candle.timestamp)
        if forced_entry is not None and candle_at < forced_entry:
            continue
        if entered_at is None:
            touched = candle.high >= entry_price if plan.direction == "LONG" else candle.low <= entry_price
            if not touched:
                continue
            entered_at = candle_at
        if plan.direction == "LONG":
            stopped = candle.low <= stop_loss
            max_favorable = max(max_favorable, candle.high - entry_price)
            max_adverse = max(max_adverse, entry_price - candle.low)
            hits = [
                target_1r is not None and candle.high >= target_1r,
                target_2r is not None and candle.high >= target_2r,
                target_3r is not None and candle.high >= target_3r,
            ]
        else:
            stopped = candle.high >= stop_loss
            max_favorable = max(max_favorable, entry_price - candle.low)
            max_adverse = max(max_adverse, candle.high - entry_price)
            hits = [
                target_1r is not None and candle.low <= target_1r,
                target_2r is not None and candle.low <= target_2r,
                target_3r is not None and candle.low <= target_3r,
            ]
        if hits[0] and hit_1r is None:
            hit_1r = candle_at
        if hits[1] and hit_2r is None:
            hit_2r = candle_at
        if hits[2] and hit_3r is None:
            hit_3r = candle_at
        if stopped:
            ambiguous = any(hits)
            stopped_at = candle_at
            return PlanEvaluation(
                "STOP",
                entry_price,
                stop_loss,
                target_1r,
                target_2r,
                target_3r,
                entered_at,
                stopped_at,
                hit_1r,
                hit_2r,
                hit_3r,
                max_favorable / risk_price,
                max_adverse / risk_price,
                ambiguous,
            )
        if hit_3r is not None:
            return PlanEvaluation(
                "3R",
                entry_price,
                stop_loss,
                target_1r,
                target_2r,
                target_3r,
                entered_at,
                None,
                hit_1r,
                hit_2r,
                hit_3r,
                max_favorable / risk_price,
                max_adverse / risk_price,
                False,
            )
    if entered_at is None:
        return PlanEvaluation(
            "NO_TRADE", entry_price, stop_loss, target_1r, target_2r, target_3r,
            None, None, None, None, None, None, None, False
        )
    return PlanEvaluation(
        "PENDING",
        entry_price,
        stop_loss,
        target_1r,
        target_2r,
        target_3r,
        entered_at,
        None,
        hit_1r,
        hit_2r,
        hit_3r,
        max_favorable / risk_price,
        max_adverse / risk_price,
        False,
    )


async def resolve_due_ml_labels(
    session: Session,
    bybit: BybitClient,
    now: datetime,
    *,
    max_snapshots: int = 20,
) -> tuple[int, int]:
    now = ensure_utc(now)
    snapshots = session.scalars(
        select(MLSignalSnapshot)
        .where(MLSignalSnapshot.observed_at <= now - timedelta(minutes=min(HORIZONS)))
        .order_by(MLSignalSnapshot.observed_at)
        .limit(max_snapshots)
    ).all()
    labels_created = results_created = 0
    for snapshot in snapshots:
        missing_horizons = [
            horizon
            for horizon in HORIZONS
            if ensure_utc(snapshot.observed_at) + timedelta(minutes=horizon) <= now
            and session.scalar(
                select(BreakoutLabel.id).where(
                    BreakoutLabel.snapshot_id == snapshot.id,
                    BreakoutLabel.horizon_minutes == horizon,
                )
            )
            is None
        ]
        missing_plan_work = [
            (plan, horizon)
            for plan in snapshot.plan_variants
            for horizon in PLAN_HORIZONS
            if ensure_utc(snapshot.observed_at) + timedelta(minutes=horizon) <= now
            and session.scalar(
                select(TradePlanResult.id).where(
                    TradePlanResult.plan_variant_id == plan.id,
                    TradePlanResult.horizon_minutes == horizon,
                )
            )
            is None
        ]
        if not missing_horizons and not missing_plan_work:
            continue
        max_horizon = max(missing_horizons + [horizon for _, horizon in missing_plan_work])
        start = ensure_utc(snapshot.observed_at)
        end = start + timedelta(minutes=max_horizon)
        try:
            m5 = await bybit.klines(
                snapshot.symbol,
                interval="5",
                limit=max(60, max_horizon // 5 + 5),
                start_ms=int(start.timestamp() * 1000),
                end_ms=int(end.timestamp() * 1000),
            )
            m1 = await bybit.klines(
                snapshot.symbol,
                interval="1",
                limit=max(300, max_horizon + 5),
                start_ms=int(start.timestamp() * 1000),
                end_ms=int(end.timestamp() * 1000),
            )
        except Exception:
            logger.exception("ml_label_market_data_failed snapshot_id=%s symbol=%s", snapshot.id, snapshot.symbol)
            continue
        _store_candles(session, snapshot.symbol, "5", m5)
        _store_candles(session, snapshot.symbol, "1", m1)
        for horizon in missing_horizons:
            cutoff = start + timedelta(minutes=horizon)
            candles = [item for item in m5 if timestamp_to_datetime(item.timestamp) <= cutoff]
            evaluation = evaluate_breakout(
                support=snapshot.support_level,
                resistance=snapshot.resistance_level,
                buffer_price=snapshot.breakout_buffer,
                candles=candles,
            )
            label = BreakoutLabel(
                snapshot_id=snapshot.id,
                horizon_minutes=horizon,
                evaluated_at=now,
                wick_breakout=evaluation.wick_breakout,
                close_breakout=evaluation.close_breakout,
                confirmed_breakout=evaluation.confirmed_breakout,
                false_breakout=evaluation.false_breakout,
                breakout_direction=evaluation.breakout_direction,
                first_breakout_at=evaluation.first_breakout_at,
                minutes_from_range_start=(
                    round((evaluation.first_breakout_at - ensure_utc(snapshot.range_start_at)).total_seconds() / 60)
                    if evaluation.first_breakout_at is not None
                    else None
                ),
                followed_preceding_trend=(
                    evaluation.breakout_direction == snapshot.direction
                    if evaluation.breakout_direction is not None
                    else None
                ),
            )
            session.add(label)
            labels_created += 1
            if evaluation.confirmed_breakout and snapshot.episode.ended_at is None:
                snapshot.episode.ended_at = evaluation.first_breakout_at or cutoff
                snapshot.episode.confirmed_breakout_at = evaluation.first_breakout_at
                snapshot.episode.confirmed_breakout_direction = evaluation.breakout_direction
                snapshot.episode.breakout_followed_trend = label.followed_preceding_trend
        for plan, horizon in missing_plan_work:
            cutoff = start + timedelta(minutes=horizon)
            evaluation = evaluate_plan(
                plan,
                [item for item in m1 if timestamp_to_datetime(item.timestamp) <= cutoff],
                [item for item in m5 if timestamp_to_datetime(item.timestamp) <= cutoff],
            )
            session.add(
                TradePlanResult(
                    plan_variant_id=plan.id,
                    horizon_minutes=horizon,
                    evaluated_at=now,
                    outcome=evaluation.outcome,
                    entry_price=evaluation.entry_price,
                    stop_loss=evaluation.stop_loss,
                    target_1r=evaluation.target_1r,
                    target_2r=evaluation.target_2r,
                    target_3r=evaluation.target_3r,
                    entered_at=evaluation.entered_at,
                    stopped_at=evaluation.stopped_at,
                    hit_1r_at=evaluation.hit_1r_at,
                    hit_2r_at=evaluation.hit_2r_at,
                    hit_3r_at=evaluation.hit_3r_at,
                    mfe_r=evaluation.mfe_r,
                    mae_r=evaluation.mae_r,
                    ambiguous_intrabar=evaluation.ambiguous_intrabar,
                )
            )
            results_created += 1
    return labels_created, results_created

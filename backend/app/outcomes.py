from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .bybit_client import BybitClient
from .config import config
from .database import DetectedSetup
from .models import Candle
from .persistence import ensure_utc


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutcomeResult:
    outcome: str
    entered_at: Optional[datetime]
    resolved_at: datetime
    price_at_deadline: Optional[float]
    mfe_r: Optional[float]
    mae_r: Optional[float]
    ambiguous_intrabar: bool = False


def candle_time(candle: Candle) -> datetime:
    return datetime.fromtimestamp(candle.timestamp / 1000, tz=timezone.utc)


def max_optional(left: Optional[float], right: Optional[float]) -> Optional[float]:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def evaluate_outcome(
    *,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    risk_price: float,
    candles: list[Candle],
    deadline: datetime,
    entered_at: Optional[datetime] = None,
) -> OutcomeResult:
    ordered = sorted(candles, key=lambda candle: candle.timestamp)
    max_favorable = 0.0
    max_adverse = 0.0

    for candle in ordered:
        entry_touched = candle.high >= entry_price if direction == "LONG" else candle.low <= entry_price
        if entered_at is None:
            if not entry_touched:
                continue
            entered_at = candle_time(candle)

        if direction == "LONG":
            stop_touched = candle.low <= stop_loss
            target_touched = candle.high >= take_profit
            max_favorable = max(max_favorable, candle.high - entry_price)
            max_adverse = max(max_adverse, entry_price - candle.low)
        else:
            stop_touched = candle.high >= stop_loss
            target_touched = candle.low <= take_profit
            max_favorable = max(max_favorable, entry_price - candle.low)
            max_adverse = max(max_adverse, candle.high - entry_price)

        ambiguous = stop_touched and target_touched
        if stop_touched:
            return OutcomeResult(
                outcome="STOP",
                entered_at=entered_at,
                resolved_at=candle_time(candle),
                price_at_deadline=candle.close,
                mfe_r=max_favorable / risk_price,
                mae_r=max_adverse / risk_price,
                ambiguous_intrabar=ambiguous,
            )
        if target_touched:
            return OutcomeResult(
                outcome="TAKE",
                entered_at=entered_at,
                resolved_at=candle_time(candle),
                price_at_deadline=candle.close,
                mfe_r=max_favorable / risk_price,
                mae_r=max_adverse / risk_price,
            )

    final_price = ordered[-1].close if ordered else None
    if entered_at is None:
        return OutcomeResult(
            outcome="NO_TRADE",
            entered_at=None,
            resolved_at=deadline,
            price_at_deadline=final_price,
            mfe_r=None,
            mae_r=None,
        )
    return OutcomeResult(
        outcome="PENDING",
        entered_at=entered_at,
        resolved_at=deadline,
        price_at_deadline=final_price,
        mfe_r=max_favorable / risk_price,
        mae_r=max_adverse / risk_price,
    )


async def resolve_due_outcomes(session: Session, bybit: BybitClient, now: datetime) -> int:
    due = session.scalars(
        select(DetectedSetup).where(
            DetectedSetup.trade_plan_status == "READY",
            DetectedSetup.outcome == "PENDING",
            DetectedSetup.outcome_deadline_at.is_not(None),
            DetectedSetup.outcome_deadline_at <= now,
        )
    ).all()
    resolved = 0
    for setup in due:
        if (
            setup.trade_plan_created_at is None
            or setup.outcome_deadline_at is None
            or setup.entry_price is None
            or setup.stop_loss is None
            or setup.take_profit is None
            or setup.risk_price is None
        ):
            continue
        start = ensure_utc(setup.resolved_at or setup.trade_plan_created_at)
        deadline = ensure_utc(now)
        minutes = max(1, round((deadline - start).total_seconds() / 60))
        try:
            candles = await bybit.klines(
                setup.symbol,
                interval="1",
                limit=min(max(200, minutes + 5), 1000),
                start_ms=int(start.timestamp() * 1000),
                end_ms=int(deadline.timestamp() * 1000),
            )
        except Exception:
            logger.exception("outcome_market_data_failed setup_id=%s symbol=%s", setup.id, setup.symbol)
            continue
        outcome = evaluate_outcome(
            direction=setup.direction,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            risk_price=setup.risk_price,
            candles=candles,
            deadline=deadline,
            entered_at=ensure_utc(setup.entered_at) if setup.entered_at is not None else None,
        )
        if outcome.outcome != "PENDING":
            setup.outcome = outcome.outcome
        else:
            setup.outcome_deadline_at = deadline + timedelta(minutes=config.scan_interval_minutes)
        setup.entered_at = outcome.entered_at or setup.entered_at
        setup.resolved_at = outcome.resolved_at
        setup.price_at_deadline = outcome.price_at_deadline
        setup.mfe_r = max_optional(setup.mfe_r, outcome.mfe_r)
        setup.mae_r = max_optional(setup.mae_r, outcome.mae_r)
        setup.ambiguous_intrabar = outcome.ambiguous_intrabar
        resolved += 1
    return resolved

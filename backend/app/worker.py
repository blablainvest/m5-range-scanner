from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from .bybit_client import BybitClient
from .config import config
from .database import ScanRun, init_db, session_scope
from .models import ScanRequest
from .ml_pipeline import persist_ml_snapshots, resolve_due_ml_labels
from .outcomes import resolve_due_outcomes
from .persistence import persist_scan
from .scanner import ScannerService


logger = logging.getLogger(__name__)


def current_schedule_slot(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    interval = max(1, config.scan_interval_minutes)
    offset = config.schedule_offset_minute_utc % interval
    minutes_since_slot = (now.minute - offset) % interval
    return now.replace(second=0, microsecond=0) - timedelta(minutes=minutes_since_slot)


def next_schedule_slot(now: datetime) -> datetime:
    current = current_schedule_slot(now)
    return current + timedelta(minutes=config.scan_interval_minutes)


async def run_cycle(scanner: ScannerService, bybit: BybitClient, scheduled_at: datetime) -> None:
    skip_scan = False
    with session_scope() as session:
        resolved = await resolve_due_outcomes(session, bybit, datetime.now(timezone.utc))
        logger.info("outcomes_resolved count=%s", resolved)
        existing = session.scalar(select(ScanRun).where(ScanRun.scheduled_at == scheduled_at))
        stale_before = datetime.now(timezone.utc) - timedelta(minutes=30)
        existing_started_at = (
            existing.started_at.replace(tzinfo=timezone.utc)
            if existing is not None and existing.started_at.tzinfo is None
            else existing.started_at if existing is not None else None
        )
        if existing is not None and (
            existing.status == "COMPLETED"
            or (existing.status == "RUNNING" and existing_started_at is not None and existing_started_at >= stale_before)
        ):
            logger.info("automatic_scan_already_exists scheduled_at=%s", scheduled_at.isoformat())
            skip_scan = True
        elif existing is None:
            session.add(
                ScanRun(
                    scheduled_at=scheduled_at,
                    started_at=datetime.now(timezone.utc),
                    status="RUNNING",
                )
            )
        elif existing is not None:
            existing.started_at = datetime.now(timezone.utc)
            existing.completed_at = None
            existing.status = "RUNNING"
            existing.error = None

    if skip_scan:
        with session_scope() as session:
            labels_created, plan_results_created = await resolve_due_ml_labels(
                session,
                bybit,
                datetime.now(timezone.utc),
            )
            logger.info(
                "ml_results_resolved labels=%s plan_results=%s",
                labels_created,
                plan_results_created,
            )
        return

    request = ScanRequest(
        force=True,
        min_rating=config.automatic_scan_min_rating,
        include_neutral=False,
        max_results=config.automatic_scan_max_results,
        turnover_24h_min=config.automatic_scan_turnover_min,
    )
    try:
        response = await scanner.scan(request)
    except Exception as exc:
        with session_scope() as session:
            run = session.scalar(select(ScanRun).where(ScanRun.scheduled_at == scheduled_at))
            if run is not None:
                run.completed_at = datetime.now(timezone.utc)
                run.status = "FAILED"
                run.error = str(exc)
        raise
    try:
        with session_scope() as session:
            v2_response = response.model_copy(
                update={
                    "results": scanner.last_background_results,
                    "signals_found": len(scanner.last_background_results),
                }
            )
            run = persist_scan(session, v2_response, scheduled_at)
            snapshots_created = persist_ml_snapshots(
                session,
                run,
                [],
                scanner.last_background_results,
            )
            logger.info(
                "automatic_scan_saved run_id=%s scheduled_at=%s ml_snapshots=%s",
                run.id,
                scheduled_at.isoformat(),
                snapshots_created,
            )
    except IntegrityError:
        logger.info("automatic_scan_already_exists scheduled_at=%s", scheduled_at.isoformat())
    with session_scope() as session:
        labels_created, plan_results_created = await resolve_due_ml_labels(
            session,
            bybit,
            datetime.now(timezone.utc),
        )
        logger.info(
            "ml_results_resolved labels=%s plan_results=%s",
            labels_created,
            plan_results_created,
        )


async def worker_loop() -> None:
    init_db()
    bybit = BybitClient()
    scanner = ScannerService(bybit)
    scheduled_slot = current_schedule_slot(datetime.now(timezone.utc))
    scan_interval = max(1, config.scan_interval_minutes)
    try:
        try:
            await run_cycle(scanner, bybit, scheduled_slot)
        except Exception:
            logger.exception("automatic_cycle_failed")
        while True:
            now = datetime.now(timezone.utc)
            next_slot = scheduled_slot + timedelta(minutes=scan_interval)
            await asyncio.sleep(max(0.0, (next_slot - now).total_seconds()))
            try:
                await run_cycle(scanner, bybit, next_slot)
            except Exception:
                logger.exception("automatic_cycle_failed scheduled_at=%s", next_slot.isoformat())
            scheduled_slot = next_slot
    finally:
        await bybit.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()

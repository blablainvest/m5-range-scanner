from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from .bybit_client import BybitClient
from .database import ScanRun, SetupObservation, init_db, session_scope
from .history import export_history_xlsx, history_candle_rows, query_history, query_setup_detail
from .models import HistoryResponse, ScanRequest, ScanResponse, ScanResult, SetupDetailResponse
from .scanner import ScannerService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bybit = BybitClient()
    app.state.scanner = ScannerService(bybit)
    try:
        yield
    finally:
        await bybit.close()


app = FastAPI(title="M5 Range Scanner", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/scan", response_model=ScanResponse)
async def scan(request: ScanRequest) -> ScanResponse:
    return await app.state.scanner.scan(request)


@app.get("/api/scans/latest", response_model=ScanResponse)
def latest_scan() -> ScanResponse:
    with session_scope() as session:
        run = session.scalar(select(ScanRun).order_by(ScanRun.scheduled_at.desc()).limit(1))
        if run is None:
            raise HTTPException(status_code=404, detail="automatic scans are not available yet")
        observations = session.scalars(
            select(SetupObservation)
            .where(SetupObservation.scan_run_id == run.id)
            .order_by(SetupObservation.rating.desc())
        ).all()
        results = [ScanResult.model_validate(observation.result_json) for observation in observations]
        return ScanResponse(
            scan_time=run.started_at.isoformat(),
            scan_duration_ms=run.scan_duration_ms or 0,
            total_symbols=run.total_symbols,
            filtered_symbols=run.analyzed_symbols,
            analyzed_symbols=run.analyzed_symbols,
            symbols_with_errors=run.symbols_with_errors,
            signals_found=len(results),
            from_cache=False,
            results=results,
        )


@app.get("/api/history", response_model=HistoryResponse)
def history(
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    outcome: Optional[str] = None,
    min_rating: Optional[int] = Query(default=None, ge=0, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> HistoryResponse:
    with session_scope() as session:
        return query_history(
            session,
            symbol=symbol,
            direction=direction,
            outcome=outcome,
            min_rating=min_rating,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )


@app.get("/api/history/export.xlsx")
def history_export(
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    outcome: Optional[str] = None,
    min_rating: Optional[int] = Query(default=None, ge=0, le=100),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> StreamingResponse:
    with session_scope() as session:
        response = query_history(
            session,
            symbol=symbol,
            direction=direction,
            outcome=outcome,
            min_rating=min_rating,
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=10_000,
        )
        candle_rows = history_candle_rows(session, [item.id for item in response.items])
        content = export_history_xlsx(response, candle_rows)
    headers = {"Content-Disposition": 'attachment; filename="m5-scanner-history.xlsx"'}
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/history/{setup_id}", response_model=SetupDetailResponse)
def history_detail(setup_id: int) -> SetupDetailResponse:
    with session_scope() as session:
        detail = query_setup_detail(session, setup_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="setup not found")
        return detail


@app.get("/api/ml/export.parquet")
def ml_export() -> StreamingResponse:
    from .ml_export import export_training_parquet

    with session_scope() as session:
        content = export_training_parquet(session)
    headers = {"Content-Disposition": 'attachment; filename="m5-scanner-v2-setups.parquet"'}
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.apache.parquet",
        headers=headers,
    )

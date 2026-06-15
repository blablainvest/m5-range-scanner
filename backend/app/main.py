from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bybit_client import BybitClient
from .models import ScanRequest, ScanResponse
from .scanner import ScannerService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bybit = BybitClient()
    app.state.scanner = ScannerService(bybit)
    try:
        yield
    finally:
        await bybit.close()


app = FastAPI(title="M5 Range Scanner", version="0.1.1", lifespan=lifespan)

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

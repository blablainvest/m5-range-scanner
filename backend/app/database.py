from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import config


class Base(DeclarativeBase):
    pass


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING")
    scan_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_symbols: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_symbols: Mapped[int] = mapped_column(Integer, default=0)
    symbols_with_errors: Mapped[int] = mapped_column(Integer, default=0)
    signals_found: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    observations: Mapped[list["SetupObservation"]] = relationship(back_populates="scan_run")


class DetectedSetup(Base):
    __tablename__ = "detected_setups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    range_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    range_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    support_level: Mapped[float] = mapped_column(Float)
    resistance_level: Mapped[float] = mapped_column(Float)
    missed_scans: Mapped[int] = mapped_column(Integer, default=0)
    trade_plan_status: Mapped[str] = mapped_column(String(32), default="NOT_APPLICABLE", index=True)
    trade_plan_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trade_plan_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trade_plan_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reward_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shelf_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shelf_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="NOT_APPLICABLE", index=True)
    entered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    price_at_deadline: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfe_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mae_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ambiguous_intrabar: Mapped[bool] = mapped_column(Boolean, default=False)

    observations: Mapped[list["SetupObservation"]] = relationship(
        back_populates="setup",
        cascade="all, delete-orphan",
        order_by="SetupObservation.observed_at",
    )


class SetupObservation(Base):
    __tablename__ = "setup_observations"
    __table_args__ = (UniqueConstraint("setup_id", "scan_run_id", name="uq_setup_observation_run"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setup_id: Mapped[int] = mapped_column(ForeignKey("detected_setups.id", ondelete="CASCADE"), index=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    setup_class: Mapped[str] = mapped_column(String(16))
    direction: Mapped[str] = mapped_column(String(16))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    range_candles_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    setup: Mapped[DetectedSetup] = relationship(back_populates="observations")
    scan_run: Mapped[ScanRun] = relationship(back_populates="observations")


class RangeEpisode(Base):
    __tablename__ = "range_episodes"
    __table_args__ = (
        UniqueConstraint("detector_version", "symbol", "started_at", name="uq_range_episode_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detector_version: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    first_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    support_level: Mapped[float] = mapped_column(Float)
    resistance_level: Mapped[float] = mapped_column(Float)
    confirmed_breakout_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    confirmed_breakout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    breakout_followed_trend: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    snapshots: Mapped[list["MLSignalSnapshot"]] = relationship(back_populates="episode")


class MLSignalSnapshot(Base):
    __tablename__ = "ml_signal_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "detector_version",
            "symbol",
            "observed_at",
            name="uq_ml_snapshot_detector_symbol_time",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("range_episodes.id", ondelete="CASCADE"), index=True)
    setup_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("detected_setups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scan_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    detector_version: Mapped[str] = mapped_column(String(32), index=True)
    feature_schema_version: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rating: Mapped[int] = mapped_column(Integer, index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    range_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    range_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    support_level: Mapped[float] = mapped_column(Float)
    resistance_level: Mapped[float] = mapped_column(Float)
    tick_size: Mapped[float] = mapped_column(Float)
    atr_14: Mapped[float] = mapped_column(Float)
    breakout_buffer: Mapped[float] = mapped_column(Float)
    range_age_minutes: Mapped[int] = mapped_column(Integer)
    funding_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_interest: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_interest_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    episode: Mapped[RangeEpisode] = relationship(back_populates="snapshots")
    labels: Mapped[list["BreakoutLabel"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )
    plan_variants: Mapped[list["TradePlanVariant"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp", name="uq_market_candle"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    turnover: Mapped[float] = mapped_column(Float)


class BreakoutLabel(Base):
    __tablename__ = "breakout_labels"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "horizon_minutes", name="uq_breakout_label_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("ml_signal_snapshots.id", ondelete="CASCADE"),
        index=True,
    )
    horizon_minutes: Mapped[int] = mapped_column(Integer, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    wick_breakout: Mapped[bool] = mapped_column(Boolean)
    close_breakout: Mapped[bool] = mapped_column(Boolean)
    confirmed_breakout: Mapped[bool] = mapped_column(Boolean)
    false_breakout: Mapped[bool] = mapped_column(Boolean)
    breakout_direction: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    first_breakout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    minutes_from_range_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    followed_preceding_trend: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    snapshot: Mapped[MLSignalSnapshot] = relationship(back_populates="labels")


class TradePlanVariant(Base):
    __tablename__ = "trade_plan_variants"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "plan_version", name="uq_snapshot_plan_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("ml_signal_snapshots.id", ondelete="CASCADE"),
        index=True,
    )
    plan_version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(String(16))
    activation: Mapped[str] = mapped_column(String(32))
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_1r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_2r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_3r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trigger_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retest_zone_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retest_zone_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    snapshot: Mapped[MLSignalSnapshot] = relationship(back_populates="plan_variants")
    results: Mapped[list["TradePlanResult"]] = relationship(
        back_populates="plan_variant",
        cascade="all, delete-orphan",
    )


class TradePlanResult(Base):
    __tablename__ = "trade_plan_results"
    __table_args__ = (
        UniqueConstraint("plan_variant_id", "horizon_minutes", name="uq_plan_result_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_variant_id: Mapped[int] = mapped_column(
        ForeignKey("trade_plan_variants.id", ondelete="CASCADE"),
        index=True,
    )
    horizon_minutes: Mapped[int] = mapped_column(Integer, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_1r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_2r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_3r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_1r_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_2r_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_3r_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mfe_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mae_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ambiguous_intrabar: Mapped[bool] = mapped_column(Boolean, default=False)

    plan_variant: Mapped[TradePlanVariant] = relationship(back_populates="results")


engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
if config.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(config.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

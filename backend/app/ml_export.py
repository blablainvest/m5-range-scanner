from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Optional

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import DetectedSetup, MLSignalSnapshot
from .detector_v2 import CANONICAL_TRADE_PLAN_VERSION, DETECTOR_VERSION


EXPORT_SCHEMA = pa.schema(
    [
        ("setup_id", pa.int64()),
        ("snapshot_id", pa.int64()),
        ("episode_id", pa.int64()),
        ("dataset_split", pa.string()),
        ("detector_version", pa.string()),
        ("feature_schema_version", pa.string()),
        ("symbol", pa.string()),
        ("observed_at", pa.string()),
        ("first_seen_at", pa.string()),
        ("last_seen_at", pa.string()),
        ("rating", pa.int64()),
        ("setup_class", pa.string()),
        ("setup_status", pa.string()),
        ("direction", pa.string()),
        ("range_start_at", pa.string()),
        ("range_end_at", pa.string()),
        ("range_age_minutes", pa.int64()),
        ("support_level", pa.float64()),
        ("resistance_level", pa.float64()),
        ("atr_14", pa.float64()),
        ("breakout_buffer", pa.float64()),
        ("price", pa.float64()),
        ("price_position", pa.float64()),
        ("range_width_pct", pa.float64()),
        ("turnover_24h_usd", pa.float64()),
        ("volume_ratio", pa.float64()),
        ("plan_version", pa.string()),
        ("plan_status", pa.string()),
        ("plan_reason", pa.string()),
        ("plan_activation", pa.string()),
        ("entry_price", pa.float64()),
        ("stop_loss", pa.float64()),
        ("risk_price", pa.float64()),
        ("target_1r", pa.float64()),
        ("target_2r", pa.float64()),
        ("target_3r", pa.float64()),
        ("outcome", pa.string()),
        ("entered_at", pa.string()),
        ("resolved_at", pa.string()),
        ("price_at_deadline", pa.float64()),
        ("mfe_r", pa.float64()),
        ("mae_r", pa.float64()),
        ("ambiguous_intrabar", pa.bool_()),
        ("features_json", pa.string()),
        ("plan_parameters_json", pa.string()),
    ]
)


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _canonical_plan_payload(features: dict[str, Any]) -> dict[str, Any]:
    variants = features.get("trade_plan_variants") or []
    if isinstance(variants, list):
        for plan in variants:
            if isinstance(plan, dict) and plan.get("version") == CANONICAL_TRADE_PLAN_VERSION:
                return plan
    return {}


def _latest_features(setup: DetectedSetup) -> tuple[dict[str, Any], Optional[int], Optional[str]]:
    if not setup.observations:
        return {}, None, None
    observation = setup.observations[-1]
    return observation.result_json or {}, observation.rating, observation.setup_class


def export_training_parquet(session: Session) -> bytes:
    setups = session.scalars(
        select(DetectedSetup)
        .options(selectinload(DetectedSetup.observations))
        .order_by(DetectedSetup.first_seen_at, DetectedSetup.id)
    ).all()
    snapshots = {
        snapshot.setup_id: snapshot
        for snapshot in session.scalars(
            select(MLSignalSnapshot).where(MLSignalSnapshot.setup_id.is_not(None))
        ).all()
        if snapshot.setup_id is not None
    }

    payload: list[dict[str, Any]] = []
    for setup in setups:
        features, rating, setup_class = _latest_features(setup)
        plan = _canonical_plan_payload(features)
        snapshot = snapshots.get(setup.id)
        episode_id = snapshot.episode_id if snapshot is not None else None
        payload.append(
            {
                "setup_id": setup.id,
                "snapshot_id": snapshot.id if snapshot is not None else None,
                "episode_id": episode_id,
                "dataset_split": (
                    "train" if episode_id is not None and episode_id % 10 < 8 else "test" if episode_id is not None else None
                ),
                "detector_version": snapshot.detector_version if snapshot is not None else DETECTOR_VERSION,
                "feature_schema_version": snapshot.feature_schema_version if snapshot is not None else None,
                "symbol": setup.symbol,
                "observed_at": _iso(setup.first_seen_at),
                "first_seen_at": _iso(setup.first_seen_at),
                "last_seen_at": _iso(setup.last_seen_at),
                "rating": rating,
                "setup_class": setup_class,
                "setup_status": features.get("setup_status"),
                "direction": setup.direction,
                "range_start_at": _iso(setup.range_start_at),
                "range_end_at": _iso(setup.range_end_at),
                "range_age_minutes": features.get("range_minutes"),
                "support_level": setup.support_level,
                "resistance_level": setup.resistance_level,
                "atr_14": features.get("atr_14"),
                "breakout_buffer": snapshot.breakout_buffer if snapshot is not None else None,
                "price": features.get("price"),
                "price_position": features.get("price_position"),
                "range_width_pct": features.get("range_width_pct"),
                "turnover_24h_usd": features.get("turnover_24h_usd"),
                "volume_ratio": features.get("volume_ratio"),
                "plan_version": setup.trade_plan_version,
                "plan_status": setup.trade_plan_status,
                "plan_reason": setup.trade_plan_reason,
                "plan_activation": plan.get("activation"),
                "entry_price": setup.entry_price,
                "stop_loss": setup.stop_loss,
                "risk_price": setup.risk_price,
                "target_1r": plan.get("target_1r"),
                "target_2r": plan.get("target_2r"),
                "target_3r": setup.take_profit,
                "outcome": setup.outcome,
                "entered_at": _iso(setup.entered_at),
                "resolved_at": _iso(setup.resolved_at),
                "price_at_deadline": setup.price_at_deadline,
                "mfe_r": setup.mfe_r,
                "mae_r": setup.mae_r,
                "ambiguous_intrabar": setup.ambiguous_intrabar,
                "features_json": json.dumps(features, ensure_ascii=False, separators=(",", ":")),
                "plan_parameters_json": json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
            }
        )

    table = pa.Table.from_pylist(payload, schema=EXPORT_SCHEMA)
    buffer = BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()

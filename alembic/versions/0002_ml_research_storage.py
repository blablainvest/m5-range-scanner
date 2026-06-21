"""ML research storage

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

from backend.app.database import Base


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "range_episodes",
    "ml_signal_snapshots",
    "market_candles",
    "breakout_labels",
    "trade_plan_variants",
    "trade_plan_results",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE VIEW ml_training_rows AS
            SELECT
                s.id AS snapshot_id,
                s.episode_id,
                s.detector_version,
                s.feature_schema_version,
                s.symbol,
                s.observed_at,
                s.rating,
                s.direction,
                s.range_start_at,
                s.range_end_at,
                s.support_level,
                s.resistance_level,
                s.tick_size,
                s.atr_14,
                s.breakout_buffer,
                s.range_age_minutes,
                s.funding_rate,
                s.open_interest,
                s.open_interest_value,
                s.features_json,
                l.horizon_minutes,
                l.wick_breakout,
                l.close_breakout,
                l.confirmed_breakout,
                l.false_breakout,
                l.breakout_direction,
                l.first_breakout_at,
                l.minutes_from_range_start,
                l.followed_preceding_trend
            FROM ml_signal_snapshots s
            JOIN breakout_labels l ON l.snapshot_id = s.id
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP VIEW IF EXISTS ml_training_rows")
    for table_name in reversed(TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)

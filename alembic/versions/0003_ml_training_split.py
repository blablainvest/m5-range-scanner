"""Add episode-safe ML dataset split

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP VIEW IF EXISTS ml_training_rows")
        op.execute(
            """
            CREATE VIEW ml_training_rows AS
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
                l.followed_preceding_trend,
                CASE WHEN mod(s.episode_id, 10) < 8 THEN 'train' ELSE 'test' END AS dataset_split
            FROM ml_signal_snapshots s
            JOIN breakout_labels l ON l.snapshot_id = s.id
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP VIEW IF EXISTS ml_training_rows")
        op.execute(
            """
            CREATE VIEW ml_training_rows AS
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

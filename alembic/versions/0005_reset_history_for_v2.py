"""Reset history for V2 strategy

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "trade_plan_results",
    "trade_plan_variants",
    "breakout_labels",
    "ml_signal_snapshots",
    "market_candles",
    "range_episodes",
    "setup_observations",
    "detected_setups",
    "scan_runs",
)


def reset_history_tables(bind) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        return

    if bind.dialect.name == "sqlite":
        bind.execute(text("PRAGMA foreign_keys=OFF"))
    for table_name in TABLES:
        bind.execute(text(f"DELETE FROM {table_name}"))
    if bind.dialect.name == "sqlite":
        bind.execute(text("PRAGMA foreign_keys=ON"))


def upgrade() -> None:
    reset_history_tables(op.get_bind())


def downgrade() -> None:
    pass

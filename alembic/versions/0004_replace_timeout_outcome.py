"""Replace timeout outcome with observed 1h

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE detected_setups SET outcome = 'PENDING' WHERE outcome IN ('TIMEOUT', 'OBSERVED_1H')")
    op.execute("UPDATE trade_plan_results SET outcome = 'PENDING' WHERE outcome IN ('TIMEOUT', 'OBSERVED_1H')")


def downgrade() -> None:
    op.execute(
        """
        UPDATE detected_setups
        SET outcome = 'TIMEOUT'
        WHERE outcome = 'PENDING'
          AND entered_at IS NOT NULL
          AND resolved_at IS NOT NULL
        """
    )
    op.execute("UPDATE trade_plan_results SET outcome = 'TIMEOUT' WHERE outcome = 'PENDING' AND entered_at IS NOT NULL")

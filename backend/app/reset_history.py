from __future__ import annotations

import logging

from sqlalchemy import text

from .database import engine


logger = logging.getLogger(__name__)

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


def table_counts(connection) -> dict[str, int]:
    return {
        table_name: int(connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
        for table_name in TABLES
    }


def reset_history(connection) -> None:
    dialect = connection.dialect.name
    if dialect == "postgresql":
        connection.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        return

    if dialect == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=OFF"))
    for table_name in TABLES:
        connection.execute(text(f"DELETE FROM {table_name}"))
    if dialect == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=ON"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with engine.begin() as connection:
        before = table_counts(connection)
        reset_history(connection)
        after = table_counts(connection)
    logger.info("History reset completed")
    logger.info("Before: %s", before)
    logger.info("After: %s", after)


if __name__ == "__main__":
    main()

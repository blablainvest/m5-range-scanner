from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


LABEL_COLUMNS = [
    "wick_breakout",
    "close_breakout",
    "confirmed_breakout",
    "false_breakout",
    "breakout_direction",
    "first_breakout_at",
    "minutes_from_range_start",
    "followed_preceding_trend",
]

ID_COLUMNS = ["episode_id", "snapshot_id", "symbol", "dataset_split"]

TIME_COLUMNS = ["observed_at", "range_start_at", "first_breakout_at"]

CATEGORICAL_COLUMNS = [
    "source_dataset_split",
    "dataset_split",
    "detector_version",
    "feature_schema_version",
    "symbol",
    "direction",
    "breakout_direction",
]

JSON_NESTED_COLUMNS = {
    "chart_candles",
    "ml_candles",
    "reasons",
    "trade_plan_variants",
    "warnings",
}

JSON_DUPLICATE_MAP = {
    "ticker": "symbol",
    "rating": "rating",
    "direction": "direction",
    "support_level": "support_level",
    "resistance_level": "resistance_level",
    "atr_14": "atr_14",
    "range_minutes": "range_age_minutes",
}

JSON_DROP_ALWAYS = {
    "bybit_url",
    "funding_rate",
    "open_interest",
    "open_interest_value",
    "range_start_timestamp",
}

JSON_TIMESTAMP_RENAME = {
    "range_end_timestamp": "feat_range_end_at",
    "trend_start_timestamp": "feat_trend_start_at",
    "trend_end_timestamp": "feat_trend_end_at",
    "shelf_start_timestamp": "feat_shelf_start_at",
    "shelf_end_timestamp": "feat_shelf_end_at",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean and flatten M5 scanner ML parquet export.")
    parser.add_argument("input", type=Path, help="Path to m5-scanner-ml-training parquet export.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/ml"),
        help="Directory for cleaned parquet files and summary report.",
    )
    return parser.parse_args()


def load_feature_records(raw: pd.Series) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, value in raw.items():
        if isinstance(value, dict):
            records.append(value)
            continue
        if not isinstance(value, str):
            raise ValueError(f"features_json at row {index} is not a JSON string or dict")
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError(f"features_json at row {index} does not contain a JSON object")
        records.append(parsed)
    return records


def normalize_base_types(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()

    if "dataset_split" in cleaned.columns:
        cleaned.insert(
            cleaned.columns.get_loc("dataset_split"),
            "source_dataset_split",
            cleaned["dataset_split"],
        )

    for column in TIME_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = pd.to_datetime(cleaned[column], errors="coerce", utc=True)

    for column in ["followed_preceding_trend"]:
        if column in cleaned.columns:
            cleaned[column] = cleaned[column].astype("boolean")

    bool_columns = [
        "wick_breakout",
        "close_breakout",
        "confirmed_breakout",
        "false_breakout",
    ]
    for column in bool_columns:
        if column in cleaned.columns:
            cleaned[column] = cleaned[column].astype("boolean")

    for column in CATEGORICAL_COLUMNS:
        if column in cleaned.columns:
            cleaned[column] = cleaned[column].astype("category")

    return cleaned


def assign_chronological_split(df: pd.DataFrame, train_ratio: float = 0.8) -> pd.DataFrame:
    cleaned = df.copy()
    if "observed_at" not in cleaned.columns:
        raise ValueError("observed_at is required for chronological train/test split")

    time_groups = (
        cleaned.groupby("observed_at", observed=True)
        .size()
        .rename("rows")
        .sort_index()
        .reset_index()
    )
    if time_groups.empty:
        raise ValueError("dataset is empty")

    target_train_rows = len(cleaned) * train_ratio
    time_groups["cum_rows"] = time_groups["rows"].cumsum()
    split_index = (time_groups["cum_rows"] - target_train_rows).abs().idxmin()
    split_time = time_groups.loc[split_index, "observed_at"]

    cleaned["dataset_split"] = "test"
    cleaned.loc[cleaned["observed_at"] <= split_time, "dataset_split"] = "train"
    cleaned["dataset_split"] = cleaned["dataset_split"].astype("category")
    return cleaned


def flatten_simple_json(records: list[dict[str, Any]], base_df: pd.DataFrame) -> pd.DataFrame:
    payload: dict[str, list[Any]] = {}

    all_keys = sorted({key for record in records for key in record.keys()})
    for key in all_keys:
        if key in JSON_NESTED_COLUMNS or key in JSON_DROP_ALWAYS:
            continue
        if key in JSON_DUPLICATE_MAP:
            continue

        values = [record.get(key) for record in records]
        if any(isinstance(value, (dict, list)) for value in values if value is not None):
            continue
        if key in JSON_TIMESTAMP_RENAME:
            payload[JSON_TIMESTAMP_RENAME[key]] = values
        else:
            payload[f"feat_{key}"] = values

    features = pd.DataFrame(payload, index=base_df.index)

    for column in features.columns:
        if column.endswith("_at"):
            features[column] = pd.to_datetime(features[column], unit="ms", errors="coerce", utc=True)
            continue
        non_null = features[column].dropna()
        if non_null.empty:
            continue
        if non_null.map(lambda value: isinstance(value, bool)).all():
            features[column] = features[column].astype("boolean")
        elif non_null.map(lambda value: isinstance(value, int) and not isinstance(value, bool)).all():
            features[column] = pd.to_numeric(features[column], errors="coerce").astype("Int64")
        elif non_null.map(lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)).all():
            features[column] = pd.to_numeric(features[column], errors="coerce")
        elif non_null.map(lambda value: isinstance(value, str)).all():
            features[column] = features[column].astype("category")

    return features


def validate_json_duplicates(df: pd.DataFrame, records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for json_key, column in JSON_DUPLICATE_MAP.items():
        mismatches = 0
        checked = 0
        for row_index, record in enumerate(records):
            if json_key not in record:
                continue
            left = record[json_key]
            right = df.iloc[row_index][column]
            if pd.isna(right) and left is None:
                continue
            checked += 1
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                if abs(float(left) - float(right)) > 1e-9:
                    mismatches += 1
            elif left != right:
                mismatches += 1
        rows.append({"json_key": json_key, "column": column, "checked": checked, "mismatches": mismatches})
    return pd.DataFrame(rows)


def validate_range_start_timestamp(df: pd.DataFrame, records: list[dict[str, Any]]) -> pd.DataFrame:
    checked = 0
    mismatches = 0
    for row_index, record in enumerate(records):
        value = record.get("range_start_timestamp")
        if value is None:
            continue
        checked += 1
        parsed = pd.to_datetime(value, unit="ms", errors="coerce", utc=True)
        if parsed != df.iloc[row_index]["range_start_at"]:
            mismatches += 1
    return pd.DataFrame(
        [
            {
                "json_key": "range_start_timestamp",
                "column": "range_start_at",
                "checked": checked,
                "mismatches": mismatches,
            }
        ]
    )


def build_candles_table(df: pd.DataFrame, records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen_snapshot_ids: set[int] = set()
    for row_index, record in enumerate(records):
        snapshot_id = int(df.iloc[row_index]["snapshot_id"])
        if snapshot_id in seen_snapshot_ids:
            continue
        seen_snapshot_ids.add(snapshot_id)
        candles = record.get("chart_candles") or []
        if not isinstance(candles, list):
            continue
        episode_id = df.iloc[row_index]["episode_id"]
        symbol = df.iloc[row_index]["symbol"]
        observed_at = df.iloc[row_index]["observed_at"]
        for candle_index, candle in enumerate(candles):
            if not isinstance(candle, dict):
                continue
            rows.append(
                {
                    "snapshot_id": snapshot_id,
                    "episode_id": episode_id,
                    "symbol": symbol,
                    "observed_at": observed_at,
                    "candle_index": candle_index,
                    "candle_at": pd.to_datetime(candle.get("timestamp"), unit="ms", utc=True, errors="coerce"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "close": candle.get("close"),
                    "volume": candle.get("volume"),
                    "turnover": candle.get("turnover"),
                }
            )
    candles_df = pd.DataFrame(rows)
    if not candles_df.empty:
        candles_df["symbol"] = candles_df["symbol"].astype("category")
    return candles_df


def constant_columns(df: pd.DataFrame, exclude: set[str] | None = None) -> list[str]:
    excluded = exclude or set()
    return [
        column
        for column in df.columns
        if column not in excluded and df[column].nunique(dropna=False) <= 1
    ]


def markdown_table(df: pd.DataFrame) -> str:
    columns = [str(column) for column in df.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in df.iterrows():
        values = [str(row[column]) for column in df.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(
    output_path: Path,
    source_path: Path,
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    model: pd.DataFrame,
    candles: pd.DataFrame,
    duplicate_check: pd.DataFrame,
    removed_constants: list[str],
) -> None:
    def clean_counts(series: pd.Series) -> dict[str, int]:
        counts = series.value_counts(dropna=False)
        return {str(key): int(value) for key, value in counts.items()}

    split_counts = clean_counts(clean["dataset_split"])
    source_split_counts = clean_counts(clean["source_dataset_split"]) if "source_dataset_split" in clean else {}
    horizon_counts = clean_counts(clean["horizon_minutes"].sort_values())
    split_summary = (
        clean.groupby("dataset_split", observed=True)
        .agg(
            rows=("dataset_split", "size"),
            snapshots=("snapshot_id", "nunique"),
            episodes=("episode_id", "nunique"),
            min_observed_at=("observed_at", "min"),
            max_observed_at=("observed_at", "max"),
        )
        .reset_index()
    )
    episode_split_counts = clean.groupby("episode_id", observed=True)["dataset_split"].nunique()
    mixed_episode_count = int((episode_split_counts > 1).sum())
    target_counts = {
        column: clean_counts(clean[column])
        for column in ["wick_breakout", "close_breakout", "confirmed_breakout", "false_breakout"]
    }
    missing = clean.isna().sum().sort_values(ascending=False)
    missing = missing[missing > 0]

    report = [
        "# M5 Scanner ML Dataset Cleanup",
        "",
        f"Source: `{source_path}`",
        "",
        "## Output Files",
        "",
        "- `m5_scanner_clean.parquet`: cleaned table with normalized types and flattened JSON features.",
        "- `m5_scanner_model_matrix.parquet`: model-oriented flat table with leakage/result columns removed from feature area and constant columns dropped.",
        "- `m5_scanner_candles.parquet`: one row per chart candle per snapshot.",
        "",
        "## Shape",
        "",
        f"- Raw: {raw.shape[0]} rows x {raw.shape[1]} columns",
        f"- Clean: {clean.shape[0]} rows x {clean.shape[1]} columns",
        f"- Model matrix: {model.shape[0]} rows x {model.shape[1]} columns",
        f"- Candles: {candles.shape[0]} rows x {candles.shape[1] if not candles.empty else 0} columns",
        "",
        "## Splits And Horizons",
        "",
        f"- Dataset split: {split_counts}",
        f"- Source dataset split before chronological reassignment: {source_split_counts}",
        f"- Horizons: {horizon_counts}",
        "",
        "## Chronological Split Summary",
        "",
        markdown_table(split_summary),
        "",
        "## Split Integrity",
        "",
        f"- Snapshot IDs split across train/test: {int((clean.groupby('snapshot_id', observed=True)['dataset_split'].nunique() > 1).sum())}",
        f"- Observed timestamps split across train/test: {int((clean.groupby('observed_at', observed=True)['dataset_split'].nunique() > 1).sum())}",
        f"- Episode IDs split across train/test: {mixed_episode_count}",
        "",
        "## Target Distribution",
        "",
    ]
    for column, counts in target_counts.items():
        report.append(f"- `{column}`: {counts}")

    report.extend(
        [
            "",
            "## Removed Constant Columns From Model Matrix",
            "",
            ", ".join(f"`{column}`" for column in removed_constants) if removed_constants else "None",
            "",
            "## Remaining Missing Values In Clean Table",
            "",
        ]
    )
    if missing.empty:
        report.append("No missing values.")
    else:
        for column, value in missing.items():
            report.append(f"- `{column}`: {int(value)}")

    report.extend(
        [
            "",
            "## JSON Duplicate Validation",
            "",
            markdown_table(duplicate_check),
            "",
            "## Notes",
            "",
            "- Date/time columns are parsed as UTC timestamps.",
            "- `dataset_split` is reassigned chronologically by whole `observed_at` groups: old rows are train, newer rows are test.",
            "- `source_dataset_split` preserves the split value from the raw export for audit only.",
            "- Nullable booleans use pandas nullable boolean dtype.",
            "- String-like status columns are stored as categories.",
            "- Top-level columns are treated as canonical when the same value is duplicated inside `features_json`.",
            "- `features_json` is kept in the clean table for traceability but removed from the model matrix.",
        ]
    )

    output_path.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    source_path = args.input.expanduser().resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw = pd.read_parquet(source_path)
    records = load_feature_records(raw["features_json"])
    base = normalize_base_types(raw)
    base = assign_chronological_split(base)
    json_features = flatten_simple_json(records, base)
    clean = pd.concat([base, json_features], axis=1)

    duplicate_check = validate_json_duplicates(clean, records)
    duplicate_check = pd.concat([duplicate_check, validate_range_start_timestamp(clean, records)], ignore_index=True)
    bad_duplicates = duplicate_check[duplicate_check["mismatches"] > 0]
    if not bad_duplicates.empty:
        raise ValueError(f"Top-level columns disagree with features_json: {bad_duplicates.to_dict('records')}")

    candles = build_candles_table(clean, records)

    leakage_columns = set(LABEL_COLUMNS + ["features_json", "source_dataset_split"])
    model = clean.drop(columns=[column for column in leakage_columns if column in clean.columns]).copy()
    for column in LABEL_COLUMNS:
        if column in clean.columns:
            model[f"target_{column}"] = clean[column]

    removed_constants = constant_columns(model, exclude=set(ID_COLUMNS + ["horizon_minutes"] + [f"target_{c}" for c in LABEL_COLUMNS]))
    model = model.drop(columns=removed_constants)

    clean_path = output_dir / "m5_scanner_clean.parquet"
    model_path = output_dir / "m5_scanner_model_matrix.parquet"
    candles_path = output_dir / "m5_scanner_candles.parquet"
    report_path = output_dir / "m5_scanner_cleanup_report.md"

    clean.to_parquet(clean_path, index=False)
    model.to_parquet(model_path, index=False)
    candles.to_parquet(candles_path, index=False)
    write_report(report_path, source_path, raw, clean, model, candles, duplicate_check, removed_constants)

    print(f"Clean table: {clean_path}")
    print(f"Model matrix: {model_path}")
    print(f"Candles table: {candles_path}")
    print(f"Report: {report_path}")
    print(f"Clean shape: {clean.shape}")
    print(f"Model shape: {model.shape}")
    print(f"Candles shape: {candles.shape}")


if __name__ == "__main__":
    main()

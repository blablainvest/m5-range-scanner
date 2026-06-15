from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.analysis import analyze_symbol
from backend.app.models import Candle, Instrument, Ticker


DEFAULT_FIXTURE = Path("tests/fixtures/v0_1_regression.json.gz")


def result_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        key: result.get(key)
        for key in (
            "rating",
            "direction",
            "support_touches",
            "resistance_touches",
            "adx_14",
            "trend_alignment",
        )
    }


def compare_fixture(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        fixture = json.load(handle)

    changes: list[dict[str, Any]] = []
    current_results = 0
    for row in fixture["symbols"]:
        instrument = Instrument.model_validate(row["instrument"])
        ticker = Ticker.model_validate(row["ticker"])
        candles = [Candle.model_validate(item) for item in row["candles"]]
        current = analyze_symbol(
            ticker,
            candles,
            instrument.tick_size,
            min_rating=0,
            include_neutral=True,
            now_ms=fixture["captured_at_ms"],
        )
        baseline = row["baseline_result"]
        if current is not None:
            current_results += 1
        current_payload = current.model_dump(by_alias=True) if current else None

        if baseline is None and current_payload is None:
            continue
        if baseline is None or current_payload is None:
            changes.append(
                {
                    "ticker": instrument.symbol,
                    "change": "added" if current_payload else "removed",
                    "baseline": result_summary(baseline),
                    "current": result_summary(current_payload),
                }
            )
            continue

        watched_fields = (
            "rating",
            "direction",
            "support_touches",
            "resistance_touches",
            "adx_14",
            "trend_alignment",
        )
        field_changes = {
            field: {"before": baseline.get(field), "after": current_payload.get(field)}
            for field in watched_fields
            if baseline.get(field) != current_payload.get(field)
        }
        if field_changes:
            changes.append(
                {
                    "ticker": instrument.symbol,
                    "change": "modified",
                    "fields": field_changes,
                    "current_confirmation": current_payload.get("direction_confirmation"),
                }
            )

    return {
        "fixture_version": fixture["version"],
        "symbols": len(fixture["symbols"]),
        "baseline_results": sum(1 for row in fixture["symbols"] if row["baseline_result"]),
        "current_results": current_results,
        "changes": changes,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Regression Report: v0.1 -> v0.1.1",
        "",
        f"- Instruments: {report['symbols']}",
        f"- v0.1 results: {report['baseline_results']}",
        f"- Current results: {report['current_results']}",
        f"- Changed instruments: {len(report['changes'])}",
        "",
        "| Ticker | Change | Explanation |",
        "| --- | --- | --- |",
    ]
    for change in report["changes"]:
        if change["change"] == "modified":
            fields = ", ".join(change["fields"].keys())
            explanation = f"Changed metrics: {fields}"
        elif change["change"] == "removed":
            explanation = "No longer passes stricter touch re-entry and/or Wilder ADX evaluation"
        else:
            explanation = "Now passes after corrected ADX or preserved trend alignment"
        lines.append(f"| {change['ticker']} | {change['change']} | {explanation} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = compare_fixture(args.fixture)
    rendered = json.dumps(report, indent=2) + "\n" if args.json else markdown_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()

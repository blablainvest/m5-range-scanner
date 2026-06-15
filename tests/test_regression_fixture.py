import gzip
import json
from pathlib import Path

from scripts.regression_compare import compare_fixture


FIXTURE_PATH = Path("tests/fixtures/v0_1_regression.json.gz")


def test_v0_1_regression_fixture_contains_50_instruments() -> None:
    with gzip.open(FIXTURE_PATH, "rt", encoding="utf-8") as handle:
        fixture = json.load(handle)

    assert fixture["version"] == "v0.1"
    assert len(fixture["symbols"]) == 50


def test_current_algorithm_runs_against_v0_1_regression_fixture() -> None:
    report = compare_fixture(FIXTURE_PATH)

    assert report["symbols"] == 50
    assert report["baseline_results"] == 22
    assert report["current_results"] > 0

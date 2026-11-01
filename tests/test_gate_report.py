"""`scripts/gate_report.py` keeps the README gate report equal to the committed baseline."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gate_report  # noqa: E402


def test_readme_report_is_in_sync_with_the_baseline():
    assert gate_report.main(["--check"]) == 0


def test_render_lists_every_field_and_the_policy():
    report = gate_report.render(
        {
            "documents": 20,
            "all_correct": 19,
            "floor": 0.9,
            "max_regression": 1,
            "prompt_version": "abc",
            "field_scores": {"b": 0.5, "a": 1.0},
        }
    )
    assert "**19/20**" in report and "`abc`" in report
    assert report.index("| a |") < report.index("| b |")

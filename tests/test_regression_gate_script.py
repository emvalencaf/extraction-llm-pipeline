"""The gate script end to end on saved extractions (no Gemini, no network)."""

import copy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("assayer")

from invoice_extraction.domain.ground_truth import ground_truth_to_extraction

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "ground_truth_51109301.json"
_spec = importlib.util.spec_from_file_location(
    "regression_gate", ROOT / "scripts/regression_gate.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

FILES = [f"invoice_{n}.pdf" for n in range(4)]


@pytest.fixture
def expected():
    return ground_truth_to_extraction(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def paths(tmp_path):
    record = FIXTURE.read_text(encoding="utf-8")
    with (tmp_path / "data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "json_data"])
        writer.writeheader()
        for name in FILES:
            writer.writerow({"filename": name, "json_data": record})
    manifest = {
        "sets": {"test": [{"invoice_no": f"n{i}", "filename": f} for i, f in enumerate(FILES)]}
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def run_gate(paths, outputs, *extra):
    saved = paths / "outputs.json"
    saved.write_text(json.dumps(outputs), encoding="utf-8")
    return gate.main(
        [
            "--csv", str(paths / "data.csv"),
            "--manifest", str(paths / "manifest.json"),
            "--baseline", str(paths / "baseline.json"),
            "--report", str(paths / "report.md"),
            "--outputs", str(saved),
            *extra,
        ]
    )  # fmt: skip


def outputs_with(expected, wrong=0, errors=0):
    """Four documents: the first `errors` have no answer, the next `wrong` are wrong."""
    result = {}
    for i, name in enumerate(FILES):
        answer = copy.deepcopy(expected)
        if i < errors:
            result[name] = {"error": "429 RESOURCE_EXHAUSTED"}
            continue
        if i < errors + wrong:
            answer["totals"]["gross_amount"] = "1.00"
        result[name] = answer
    return result


def write_baseline(paths, all_correct=4, floor=0.5):
    data = {"documents": 4, "all_correct": all_correct, "floor": floor, "max_regression": 1,
            "field_scores": {"invoice_no": 1.0}}  # fmt: skip
    (paths / "baseline.json").write_text(json.dumps(data), encoding="utf-8")


def test_matching_run_passes_and_writes_the_report(paths, expected):
    write_baseline(paths)
    assert run_gate(paths, outputs_with(expected)) == 0
    assert "Regression gate: PASS" in (paths / "report.md").read_text(encoding="utf-8")


def test_regression_beyond_one_document_exits_1(paths, expected):
    write_baseline(paths)
    assert run_gate(paths, outputs_with(expected, wrong=2)) == 1
    assert "REGRESSION" in (paths / "report.md").read_text(encoding="utf-8")


def test_one_document_regression_is_tolerated(paths, expected):
    write_baseline(paths)
    assert run_gate(paths, outputs_with(expected, wrong=1)) == 0


def test_floor_breach_exits_1(paths, expected):
    write_baseline(paths, all_correct=2, floor=0.75)
    assert run_gate(paths, outputs_with(expected, wrong=2)) == 1
    assert "FLOOR" in (paths / "report.md").read_text(encoding="utf-8")


def test_quota_error_is_inconclusive_and_fails(paths, expected):
    write_baseline(paths)
    assert run_gate(paths, outputs_with(expected, errors=1)) == 1
    report = (paths / "report.md").read_text(encoding="utf-8")
    assert "INCONCLUSIVE" in report and "429 RESOURCE_EXHAUSTED" in report


def test_missing_result_is_inconclusive(paths, expected):
    write_baseline(paths)
    partial = outputs_with(expected)
    del partial[FILES[0]]
    assert run_gate(paths, partial) == 1


def test_a_business_failure_counts_as_wrong_not_inconclusive(paths, expected):
    write_baseline(paths)
    outputs = outputs_with(expected)
    outputs[FILES[0]] = None  # the pipeline ended failed_validation
    outputs[FILES[1]] = None
    assert run_gate(paths, outputs) == 1
    assert "REGRESSION" in (paths / "report.md").read_text(encoding="utf-8")


def test_no_baseline_exits_2(paths, expected):
    assert run_gate(paths, outputs_with(expected)) == 2


def test_update_baseline_writes_the_file_and_keeps_the_policy(paths, expected):
    write_baseline(paths, all_correct=1, floor=0.6)
    assert run_gate(paths, outputs_with(expected, wrong=1), "--update-baseline") == 0
    saved = json.loads((paths / "baseline.json").read_text(encoding="utf-8"))
    assert saved["all_correct"] == 3 and saved["documents"] == 4 and saved["floor"] == 0.6
    assert saved["field_scores"]["totals.gross_amount"] == 0.75


def test_update_baseline_refuses_an_inconclusive_run(paths, expected):
    assert run_gate(paths, outputs_with(expected, errors=1), "--update-baseline") == 1
    assert not (paths / "baseline.json").exists()


def test_model_calls_are_spaced_to_the_requested_rate():
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    class Inner:
        def extract(self, request):
            return "reply"

    model = gate.RateLimitedModel(Inner(), rpm=12, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        model.extract(None)
    assert slept == [5.0, 5.0]  # 12 RPM is one call every 5 s; the first goes at once

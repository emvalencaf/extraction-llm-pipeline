"""Seam 3: the gate verdict and report for baseline vs. run inputs."""

import json

from invoice_extraction.domain.gate import (
    Baseline,
    DocumentOutcome,
    GateRun,
    GateStatus,
    baseline_from_run,
    evaluate,
    render_report,
)

FIELDS = ("invoice_no", "totals.gross_amount", "items.list_f1")


def doc(n: int, correct: bool = True, *, conclusive: bool = True) -> DocumentOutcome:
    scores = {k: (1.0 if correct else 0.0) for k in FIELDS} if conclusive else {}
    return DocumentOutcome(f"inv-{n}", conclusive, correct and conclusive, scores)


def run_with(correct: int, total: int = 20) -> GateRun:
    return GateRun(tuple(doc(i, i < correct) for i in range(total)), expected_documents=total)


def baseline(correct: int = 18, total: int = 20, floor: float = 0.7) -> Baseline:
    return baseline_from_run(run_with(correct, total), floor=floor)


def test_run_equal_to_baseline_passes():
    verdict = evaluate(baseline(18), run_with(18))
    assert verdict.status is GateStatus.PASS
    assert verdict.passed


def test_one_document_regression_is_noise_and_passes():
    assert evaluate(baseline(18), run_with(17)).status is GateStatus.PASS


def test_improvement_passes():
    assert evaluate(baseline(15), run_with(19)).status is GateStatus.PASS


def test_regression_of_more_than_one_document_fails():
    verdict = evaluate(baseline(18), run_with(16))
    assert verdict.status is GateStatus.REGRESSION
    assert not verdict.passed
    assert "2" in verdict.reasons[0]


def test_below_absolute_floor_fails_even_if_baseline_is_low():
    verdict = evaluate(baseline(12, floor=0.7), run_with(12))
    assert verdict.status is GateStatus.FLOOR


def test_floor_boundary_is_inclusive():
    assert evaluate(baseline(14, floor=0.7), run_with(14)).status is GateStatus.PASS


def test_failing_both_reports_floor_first_and_lists_both_reasons():
    verdict = evaluate(baseline(18, floor=0.7), run_with(10))
    assert verdict.status is GateStatus.FLOOR
    assert len(verdict.reasons) == 2


def test_an_inconclusive_document_fails_the_run():
    outcomes = [doc(i) for i in range(19)] + [doc(19, conclusive=False)]
    verdict = evaluate(baseline(18), GateRun(tuple(outcomes), expected_documents=20))
    assert verdict.status is GateStatus.INCONCLUSIVE
    assert not verdict.passed


def test_missing_documents_are_inconclusive():
    short = GateRun(tuple(doc(i) for i in range(15)), expected_documents=20)
    assert evaluate(baseline(18), short).status is GateStatus.INCONCLUSIVE


def test_inconclusive_wins_over_a_regression():
    outcomes = [doc(i, False) for i in range(19)] + [doc(19, conclusive=False)]
    verdict = evaluate(baseline(18), GateRun(tuple(outcomes), expected_documents=20))
    assert verdict.status is GateStatus.INCONCLUSIVE


def test_baseline_for_another_test_set_size_is_inconclusive():
    assert evaluate(baseline(9, total=10), run_with(18)).status is GateStatus.INCONCLUSIVE


def test_report_shows_verdict_deltas_and_failing_documents():
    verdict = evaluate(baseline(18), run_with(16))
    report = render_report(baseline(18), run_with(16), verdict)
    assert "<!-- regression-gate -->" in report
    assert "REGRESSION" in report
    assert "16/20" in report and "18/20" in report
    assert "totals.gross_amount" in report
    assert "inv-16" in report  # a document that is not all-correct


def test_report_lists_inconclusive_documents_with_their_note():
    outcomes = [doc(i) for i in range(19)] + [
        DocumentOutcome("inv-19", False, False, {}, note="429 quota exhausted")
    ]
    gate_run = GateRun(tuple(outcomes), expected_documents=20)
    report = render_report(baseline(18), gate_run, evaluate(baseline(18), gate_run))
    assert "INCONCLUSIVE" in report and "429 quota exhausted" in report


def test_baseline_from_run_averages_fields_and_round_trips_json():
    gate_run = run_with(18)
    new = baseline_from_run(gate_run, floor=0.6, prompt_version="abc")
    assert new.documents == 20 and new.all_correct == 18 and new.floor == 0.6
    assert new.field_scores["invoice_no"] == 0.9
    assert Baseline.from_json(json.loads(json.dumps(new.to_json()))) == new

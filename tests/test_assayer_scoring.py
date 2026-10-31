"""Scoring a document with assayer: deterministic metrics, formats normalized first."""

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("assayer")

from invoice_extraction.adapters.assayer_scoring import score_document
from invoice_extraction.domain.ground_truth import ground_truth_to_extraction

FIXTURE = Path(__file__).parent / "fixtures" / "ground_truth_51109301.json"


@pytest.fixture
def expected():
    return ground_truth_to_extraction(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_identical_extraction_is_all_correct(expected):
    outcome = score_document("51109301", expected, copy.deepcopy(expected))
    assert outcome.conclusive and outcome.all_correct
    assert outcome.field_scores["invoice_no"] == 1.0
    assert outcome.field_scores["items.list_f1"] == 1.0


def test_amount_and_date_formats_do_not_matter(expected):
    other = copy.deepcopy(expected)
    other["issue_date"] = "2023-07-03"  # the label says 03/07/2023
    other["totals"]["gross_amount"] = "INR 1844673.60"
    assert score_document("51109301", expected, other).all_correct


def test_a_wrong_field_and_a_wrong_line_item_are_visible_per_field(expected):
    other = copy.deepcopy(expected)
    other["totals"]["gross_amount"] = "1.00"
    other["items"][0]["quantity"] = "99"
    outcome = score_document("51109301", expected, other)
    assert not outcome.all_correct
    assert outcome.field_scores["totals.gross_amount"] == 0.0
    assert outcome.field_scores["items.quantity"] < 1.0  # one item of several is wrong
    assert outcome.field_scores["invoice_no"] == 1.0


def test_no_extraction_scores_zero_but_stays_conclusive(expected):
    outcome = score_document("51109301", expected, None)
    assert outcome.conclusive and not outcome.all_correct
    assert set(outcome.field_scores.values()) == {0.0}

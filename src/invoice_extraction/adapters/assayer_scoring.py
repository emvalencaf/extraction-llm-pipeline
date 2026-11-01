"""Score one extraction against its ground truth with assayer's deterministic metrics.

assayer is used as-is (see `docs/assayer-required-changes.md`): no judges, no LangSmith.
It is a dev/CI dependency only, so it is imported inside the functions and never reaches
the Lambda image.

Both sides go through the Extraction Schema first, so amounts compare as numbers and dates
as ISO dates whatever format the label or the model used (assayer has no such metric: G1,
G2). Amounts become floats, which `numeric_tolerance` needs; the tolerance is half a cent.
"""

from typing import Any

from pydantic import ValidationError

from invoice_extraction.domain.gate import DocumentOutcome
from invoice_extraction.domain.schema import Extraction

AMOUNT_TOLERANCE = 0.005
_TEXT = ["normalized_exact_match"]
_AMOUNT = [{"numeric_tolerance": {"tolerance": AMOUNT_TOLERANCE}}]
_PARTY = {"name": _TEXT, "address": _TEXT, "tax_id": _TEXT}
_ITEM_FIELDS = {
    "description": _TEXT,
    "quantity": _AMOUNT,
    "unit": _TEXT,
    "unit_price": _AMOUNT,
    "net_amount": _AMOUNT,
    "vat_pct": _AMOUNT,
    "gross_amount": _AMOUNT,
}
_TOTALS_FIELDS = {
    "vat_pct": _AMOUNT,
    "net_amount": _AMOUNT,
    "vat_amount": _AMOUNT,
    "gross_amount": _AMOUNT,
}

FIELD_MAP: dict[str, Any] = {
    "invoice_no": _TEXT,
    "issue_date": ["exact_match"],
    "currency": ["exact_match"],
    **{
        f"{side}.{name}": metrics
        for side in ("seller", "client")
        for name, metrics in _PARTY.items()
    },
    **{f"totals.{name}": metrics for name, metrics in _TOTALS_FIELDS.items()},
    # an invoice lists its items in a fixed order, so pair them by position
    "items": {"align": "positional", "properties": _ITEM_FIELDS},
}

# Every field compared as a number: canonical() turns these into floats.
_AMOUNT_KEYS = frozenset(
    name for fields in (_ITEM_FIELDS, _TOTALS_FIELDS) for name, m in fields.items() if m is _AMOUNT
)


def canonical(extraction: dict[str, Any] | Extraction) -> dict[str, Any]:
    """Normalized, JSON-comparable form: amounts as floats, dates as ISO strings."""
    model = (
        extraction if isinstance(extraction, Extraction) else Extraction.model_validate(extraction)
    )
    data = model.model_dump(mode="json")  # Decimal and date become strings

    def amounts_as_floats(node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {k: amounts_as_floats(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [amounts_as_floats(v, key) for v in node]
        if key in _AMOUNT_KEYS and isinstance(node, str):
            return float(node)
        return node

    return amounts_as_floats(data)


def score_document(
    invoice_no: str, expected: dict[str, Any], predicted: Extraction | dict[str, Any] | None
) -> DocumentOutcome:
    """A conclusive outcome: `predicted` None means the pipeline answered with no Extraction
    (a business failure), and an answer that is no valid Extraction counts the same; both
    score zero on every field (the latter is noted)."""
    from assayer.models import Case, Dataset
    from assayer.runner import Runner, parse_field_map

    case = Case(input=invoice_no, id=invoice_no, expected_output=canonical(expected))
    note = ""
    answer: dict[str, Any] = {"items": []}
    if predicted is not None:
        try:
            answer = canonical(predicted)
        except ValidationError:
            predicted, note = None, "invalid extraction"
    experiment = Runner(lambda _: answer, field_metrics=parse_field_map(FIELD_MAP)).run(
        Dataset("invoices", [case])
    )
    if experiment.failures:
        return DocumentOutcome(invoice_no, False, note=f"scoring failed: {experiment.failures[0]}")
    scores: dict[str, float] = {}
    for field_name, field_scores in experiment.scores_by_field().items():
        for score in field_scores:
            key = f"{field_name}.{score.name}" if score.name.startswith("list_") else field_name
            scores[key] = float(score.value)
    if predicted is None:
        scores = dict.fromkeys(scores, 0.0)
    return DocumentOutcome(
        invoice_no,
        True,
        all_correct=predicted is not None and all(v >= 1.0 for v in scores.values()),
        field_scores=scores,
        note=note,
    )

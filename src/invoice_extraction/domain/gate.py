"""The regression gate verdict: baseline vs. run, no I/O and no LLM judge.

A run is one outcome per Test Set document. A document is *conclusive* when the pipeline
produced an answer (even a wrong one or a `failed_validation`); it is inconclusive when no
answer was obtained (quota errors, crash, missing result). Inconclusive always fails: a flaky
run must never let a regression through.

Verdict rules, in priority order:

1. INCONCLUSIVE: any document inconclusive, fewer outcomes than the Test Set, or a baseline
   recorded for a Test Set of another size.
2. FLOOR: the all-correct rate is below the baseline's absolute floor.
3. REGRESSION: more than `max_regression` documents fewer all-correct than the baseline.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

REPORT_MARKER = "<!-- regression-gate -->"  # lets CI update one sticky PR comment
DEFAULT_FLOOR = 0.7
DEFAULT_MAX_REGRESSION = 1


class GateStatus(Enum):
    PASS = "pass"
    INCONCLUSIVE = "inconclusive"
    FLOOR = "floor"
    REGRESSION = "regression"


@dataclass(frozen=True)
class DocumentOutcome:
    invoice_no: str
    conclusive: bool
    all_correct: bool = False
    field_scores: Mapping[str, float] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class GateRun:
    documents: tuple[DocumentOutcome, ...]
    expected_documents: int  # size of the Test Set

    @property
    def all_correct(self) -> int:
        return sum(1 for d in self.documents if d.conclusive and d.all_correct)

    @property
    def inconclusive(self) -> tuple[DocumentOutcome, ...]:
        return tuple(d for d in self.documents if not d.conclusive)

    def field_means(self) -> dict[str, float]:
        scored = [d.field_scores for d in self.documents if d.conclusive]
        names = sorted({name for scores in scored for name in scores})
        return {
            name: round(sum(s.get(name, 0.0) for s in scored) / len(scored), 4) for name in names
        }


@dataclass(frozen=True)
class Baseline:
    """The committed `baseline.json`: the accepted result plus the gate policy."""

    documents: int
    all_correct: int
    field_scores: Mapping[str, float]
    floor: float = DEFAULT_FLOOR
    max_regression: int = DEFAULT_MAX_REGRESSION
    prompt_version: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "all_correct": self.all_correct,
            "floor": self.floor,
            "max_regression": self.max_regression,
            "prompt_version": self.prompt_version,
            "field_scores": dict(self.field_scores),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Baseline":
        return cls(
            documents=data["documents"],
            all_correct=data["all_correct"],
            field_scores=dict(data["field_scores"]),
            floor=data.get("floor", DEFAULT_FLOOR),
            max_regression=data.get("max_regression", DEFAULT_MAX_REGRESSION),
            prompt_version=data.get("prompt_version"),
        )


def baseline_from_run(
    run: GateRun,
    *,
    floor: float = DEFAULT_FLOOR,
    max_regression: int = DEFAULT_MAX_REGRESSION,
    prompt_version: str | None = None,
) -> Baseline:
    return Baseline(
        documents=len(run.documents),
        all_correct=run.all_correct,
        field_scores=run.field_means(),
        floor=floor,
        max_regression=max_regression,
        prompt_version=prompt_version,
    )


@dataclass(frozen=True)
class Verdict:
    status: GateStatus
    reasons: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status is GateStatus.PASS


def evaluate(baseline: Baseline, run: GateRun) -> Verdict:
    unusable = []
    if len(run.documents) < run.expected_documents:
        unusable.append(f"{len(run.documents)} of {run.expected_documents} documents have a result")
    if run.inconclusive:
        unusable.append(f"{len(run.inconclusive)} document(s) inconclusive")
    if baseline.documents != run.expected_documents:
        unusable.append(
            f"baseline covers {baseline.documents} documents, the Test Set has "
            f"{run.expected_documents}"
        )
    if unusable:
        return Verdict(GateStatus.INCONCLUSIVE, tuple(unusable))

    reasons: list[tuple[GateStatus, str]] = []
    rate = run.all_correct / run.expected_documents
    if rate < baseline.floor:
        reasons.append(
            (GateStatus.FLOOR, f"all-correct rate {rate:.0%} is below the floor {baseline.floor:.0%}")
        )
    dropped = baseline.all_correct - run.all_correct
    if dropped > baseline.max_regression:
        reasons.append(
            (
                GateStatus.REGRESSION,
                f"{dropped} fewer all-correct documents than the baseline "
                f"(allowed: {baseline.max_regression})",
            )
        )
    if not reasons:
        return Verdict(GateStatus.PASS)
    return Verdict(reasons[0][0], tuple(text for _, text in reasons))


def render_report(baseline: Baseline, run: GateRun, verdict: Verdict) -> str:
    """Markdown for the sticky PR comment and the job summary."""
    total = run.expected_documents
    lines = [
        REPORT_MARKER,
        f"## Regression gate: {verdict.status.name}",
        "",
        *[f"- {reason}" for reason in verdict.reasons],
        "",
        f"All-correct documents: {run.all_correct}/{total} (baseline "
        f"{baseline.all_correct}/{baseline.documents}, floor {baseline.floor:.0%}, "
        f"tolerated drop {baseline.max_regression})",
        "",
    ]
    if run.inconclusive:
        lines += ["### Inconclusive documents", ""]
        lines += [f"- `{d.invoice_no}`: {d.note or 'no result'}" for d in run.inconclusive]
        lines.append("")
    means = run.field_means()
    if means:
        lines += ["### Per-field score", "", "| Field | Baseline | Run | Delta |", "|---|---|---|---|"]
        for name in sorted(set(means) | set(baseline.field_scores)):
            before, after = baseline.field_scores.get(name), means.get(name)
            delta = "" if before is None or after is None else f"{after - before:+.4f}"
            lines.append(f"| {name} | {_fmt(before)} | {_fmt(after)} | {delta} |")
        lines.append("")
    wrong = [d for d in run.documents if d.conclusive and not d.all_correct]
    if wrong:
        lines += ["### Documents not all-correct", ""]
        for d in wrong:
            failing = sorted(n for n, s in d.field_scores.items() if s < 1.0)
            detail = d.note or ", ".join(failing)
            lines.append(f"- `{d.invoice_no}`: {detail}")
        lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"

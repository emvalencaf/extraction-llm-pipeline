# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "llm-assayer-eval>=0.1.1",
#   "google-genai>=2.34.0",
#   "langgraph>=1.0",
#   "presidio-analyzer>=2.2.366",
#   "pydantic>=2.14.2",
#   "pypdf>=6.21.4",
#   "spacy",
# ]
# ///
"""Regression gate: run the real graph on the Test Set and compare with `data/baseline.json`.

Usage:
    uv run scripts/regression_gate.py                      # gate; exit 1 on a failing verdict
    uv run scripts/regression_gate.py --update-baseline    # accept this run as the new baseline
    uv run scripts/regression_gate.py --outputs saved.json # score saved extractions, no Gemini

Needs the Kaggle dataset (git-ignored) under data/kaggle and, for a live run, the key of the
gate's own Google project in GATE_GEMINI_API_KEY (kept apart from the service key so the
gate neither exceeds the service quota nor competes with it). The graph runs with the
temperatures of the Prompt Bundle (0) and the model calls are paced to --rpm (12 by default,
under the free tier's 15).

Exit codes: 0 pass (or baseline written), 1 failing verdict, 2 usage error or no baseline.
No LLM judge is used: scoring is assayer's deterministic field metrics. The verdict rules
are in `invoice_extraction.domain.gate`; the baseline update is a plain file change, so it
is reviewed in the PR like any other diff.
"""

import argparse
import csv
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from invoice_extraction.adapters.assayer_scoring import score_document  # noqa: E402
from invoice_extraction.application.ports import ExtractionModel  # noqa: E402
from invoice_extraction.domain.gate import (  # noqa: E402
    Baseline,
    DocumentOutcome,
    GateRun,
    GateStatus,
    baseline_from_run,
    evaluate,
    render_report,
)
from invoice_extraction.domain.ground_truth import ground_truth_to_extraction  # noqa: E402

DEFAULT_RPM = 12
ERROR_KEY = "error"


@dataclass(frozen=True)
class TestDocument:
    """One Test Set document: its id, its PDF and the Extraction-shaped ground truth."""

    __test__ = False  # not a pytest class

    invoice_no: str
    filename: str
    expected: dict[str, Any]


class RateLimitedModel:
    """Spaces the model calls at least 60/rpm seconds apart."""

    def __init__(
        self,
        inner: ExtractionModel,
        rpm: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._inner, self._interval = inner, 60.0 / rpm
        self._clock, self._sleep = clock, sleep
        self._next_at = 0.0

    def extract(self, request):
        wait = self._next_at - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._next_at = self._clock() + self._interval
        return self._inner.extract(request)


def load_test_set(csv_path: Path, manifest_path: Path) -> list[TestDocument]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = {row["filename"]: row for row in csv.DictReader(handle)}
    return [
        TestDocument(
            entry["invoice_no"],
            entry["filename"],
            ground_truth_to_extraction(json.loads(rows[entry["filename"]]["json_data"])),
        )
        for entry in manifest["sets"]["test"]
    ]


def graph_runner(extract: Any, pdf_dir: Path) -> Callable[[str], dict[str, Any] | None]:
    """Run the real graph on a PDF found under `pdf_dir`: filename -> Extraction dict or None.

    A business failure (unreadable PDF, schema still invalid) is a None answer. An outage of
    the models (quota exhausted, `ModelUnavailableError`) raises, so it stays inconclusive.
    """

    def run(filename: str) -> dict[str, Any] | None:
        found = next(pdf_dir.rglob(filename), None)
        if found is None:
            raise FileNotFoundError(f"{filename} not found under {pdf_dir}")
        result = extract(found.read_bytes())
        return result.extraction.model_dump(mode="json") if result.extraction else None

    return run


def live_extractor(pdf_dir: Path, rpm: float) -> tuple[Callable[[str], Any], str]:
    """Run the real graph on Gemini; returns (runner, prompt version)."""
    from google import genai

    from invoice_extraction.adapters.gemini import GeminiExtractionModel
    from invoice_extraction.composition.container import build_extract_invoice

    key = os.environ.get("GATE_GEMINI_API_KEY")
    if not key:
        sys.exit("GATE_GEMINI_API_KEY is not set (the gate uses its own Google project)")
    model = RateLimitedModel(GeminiExtractionModel(genai.Client(api_key=key)), rpm)
    extract = build_extract_invoice(model)
    return graph_runner(extract, pdf_dir), extract.prompt_version


def replay_extractor(path: Path) -> Callable[[str], Any]:
    """Saved outputs: {filename: extraction | null | {"error": "..."}}; absent means no result."""
    saved = json.loads(path.read_text(encoding="utf-8"))

    def run(filename: str) -> Any:
        if filename not in saved:
            raise LookupError("no saved output")
        value = saved[filename]
        if isinstance(value, dict) and ERROR_KEY in value and len(value) == 1:
            raise RuntimeError(value[ERROR_KEY])
        return value

    return run


def collect_run(test_set: list[TestDocument], extract: Callable[[str], Any]) -> GateRun:
    """Score every Test Set document. Any failure to obtain an answer is inconclusive;
    an answer that is no valid Extraction, or none, is a conclusive miss (`score_document`)."""
    outcomes = []
    for document in test_set:
        try:
            answer = extract(document.filename)
        except Exception as error:
            outcomes.append(
                DocumentOutcome(document.invoice_no, False, note=f"{type(error).__name__}: {error}")
            )
            continue
        outcomes.append(score_document(document.invoice_no, document.expected, answer))
    return GateRun(tuple(outcomes), expected_documents=len(test_set))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, default=ROOT / "data/kaggle/Batch 1/batch_1.csv")
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / "data/kaggle/Batch 1")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/split_manifest.json")
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/baseline.json")
    parser.add_argument("--report", type=Path, default=ROOT / "gate-report.md")
    parser.add_argument("--rpm", type=float, default=DEFAULT_RPM)
    parser.add_argument(
        "--outputs", type=Path, help="score saved extractions instead of calling Gemini"
    )
    parser.add_argument("--save-outputs", type=Path, help="write the raw extractions of a live run")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    test_set = load_test_set(args.csv, args.manifest)
    prompt_version = None
    if args.outputs:
        extract = replay_extractor(args.outputs)
    else:
        extract, prompt_version = live_extractor(args.pdf_dir, args.rpm)
    recorded: dict[str, Any] = {}

    def recording(filename: str) -> Any:
        recorded[filename] = value = extract(filename)
        return value

    run = collect_run(test_set, recording)
    if args.save_outputs:
        args.save_outputs.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")

    existing = (
        Baseline.from_json(json.loads(args.baseline.read_text(encoding="utf-8")))
        if args.baseline.exists()
        else None
    )
    if args.update_baseline:
        if run.inconclusive or len(run.documents) < run.expected_documents:
            print("refusing to update the baseline from an inconclusive run", file=sys.stderr)
            args.report.write_text(_inconclusive_report(run), encoding="utf-8")
            return 1
        policy = (
            {"floor": existing.floor, "max_regression": existing.max_regression} if existing else {}
        )
        new = baseline_from_run(run, prompt_version=prompt_version, **policy)
        args.baseline.write_text(json.dumps(new.to_json(), indent=2) + "\n", encoding="utf-8")
        print(f"baseline updated: {new.all_correct}/{new.documents} all-correct; review the diff")
        return 0

    if existing is None:
        print(f"no baseline at {args.baseline}; run once with --update-baseline", file=sys.stderr)
        return 2
    verdict = evaluate(existing, run)
    report = render_report(existing, run, verdict)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    return 0 if verdict.status is GateStatus.PASS else 1


def _inconclusive_report(run: GateRun) -> str:
    baseline = baseline_from_run(run)
    return render_report(baseline, run, evaluate(baseline, run))


if __name__ == "__main__":
    sys.exit(main())

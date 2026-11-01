# /// script
# requires-python = ">=3.11"
# dependencies = ["presidio-analyzer>=2.2.366", "spacy"]
# ///
"""Regenerate the static few-shot examples of the Prompt Bundle from the Train Set.

Usage: uv run scripts/build_fewshots.py [--csv PATH] [--items 1,3,6]

Picks, for each wanted line-item count, the first Train Set invoice (Split Manifest order)
and maps its ground truth with `ground_truth_to_extraction`. Validation and Test Set
invoices are never read. Needs the Kaggle CSV (git-ignored) under data/kaggle.

Real inputs reach the model anonymized, so the examples are anonymized the same way: the
text goes through the Presidio detector and `anonymize` (plus the ground-truth party names
and tax ids, which the detector cannot always spot), and every string of the expected
extraction is rewritten with the very same `[TYPE_n]` tokens.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from invoice_extraction.adapters.presidio_detector import PresidioDetector  # noqa: E402
from invoice_extraction.application.ports import SensitiveSpan  # noqa: E402
from invoice_extraction.application.privacy import PlaceholderMap, anonymize  # noqa: E402
from invoice_extraction.domain.ground_truth import ground_truth_to_extraction  # noqa: E402

OUTPUT = ROOT / "src" / "invoice_extraction" / "prompts" / "examples.json"


def _known_spans(text: str, extraction: dict) -> list[SensitiveSpan]:
    """Party names and tax ids from the ground truth, wherever they occur in the text."""
    spans = []
    for party in (extraction["seller"], extraction["client"]):
        for field, kind in (("name", "NAME"), ("tax_id", "TAX_ID")):
            value = party[field]
            start = text.find(value) if value else -1
            while start != -1:
                spans.append(SensitiveSpan(start, start + len(value), kind))
                start = text.find(value, start + len(value))
    return spans


def _rewrite(value, placeholders: PlaceholderMap):
    """Replace every sensitive value of the map in every string, longest value first."""
    if isinstance(value, str):
        pairs = sorted(
            ((placeholders.value_of(t), t) for t in placeholders.tokens()),
            key=lambda pair: -len(pair[0]),
        )
        for raw, token in pairs:
            value = value.replace(raw, token)
        return value
    if isinstance(value, list):
        return [_rewrite(v, placeholders) for v in value]
    if isinstance(value, dict):
        return {k: _rewrite(v, placeholders) for k, v in value.items()}
    return value


def anonymize_example(text: str, extraction: dict, detector: PresidioDetector) -> tuple[str, dict]:
    spans = detector.detect(text) + _known_spans(text, extraction)
    anonymized, placeholders = anonymize(text, spans)
    return anonymized, _rewrite(extraction, placeholders)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/kaggle/Batch 1/batch_1.csv")
    parser.add_argument("--items", default="1,3,6", help="wanted line-item counts")
    args = parser.parse_args()

    manifest = json.loads((ROOT / "data/split_manifest.json").read_text(encoding="utf-8"))
    train = [entry["filename"] for entry in manifest["sets"]["train"]]
    with args.csv.open(newline="", encoding="utf-8") as handle:
        rows = {row["filename"]: row for row in csv.DictReader(handle)}

    wanted = [int(n) for n in args.items.split(",")]
    detector = PresidioDetector()
    examples = []
    for count in wanted:
        for filename in train:
            record = json.loads(rows[filename]["json_data"])
            if len(record["items"]) == count:
                text, extraction = anonymize_example(
                    rows[filename]["ocred_text"], ground_truth_to_extraction(record), detector
                )
                examples.append(
                    {"invoice_no": record["invoice_no"], "text": text, "extraction": extraction}
                )
                break
        else:
            sys.exit(f"no Train Set invoice with {count} line items")
    OUTPUT.write_text(json.dumps(examples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} examples to {OUTPUT}")


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Regenerate the static few-shot examples of the Prompt Bundle from the Train Set.

Usage: uv run scripts/build_fewshots.py [--csv PATH] [--items 1,3,6]

Picks, for each wanted line-item count, the first Train Set invoice (Split Manifest order)
and maps its ground truth with `ground_truth_to_extraction`. Validation and Test Set
invoices are never read. Needs the Kaggle CSV (git-ignored) under data/kaggle.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from invoice_extraction.domain.ground_truth import ground_truth_to_extraction  # noqa: E402

OUTPUT = ROOT / "src" / "invoice_extraction" / "prompts" / "examples.json"


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
    examples = []
    for count in wanted:
        for filename in train:
            record = json.loads(rows[filename]["json_data"])
            if len(record["items"]) == count:
                examples.append(
                    {
                        "invoice_no": record["invoice_no"],
                        "text": rows[filename]["ocred_text"],
                        "extraction": ground_truth_to_extraction(record),
                    }
                )
                break
        else:
            sys.exit(f"no Train Set invoice with {count} line items")
    OUTPUT.write_text(json.dumps(examples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} examples to {OUTPUT}")


if __name__ == "__main__":
    main()

"""Build the committed Split Manifest from the downloaded Kaggle invoices.

Deterministic: seeded shuffle inside each item-count stratum, then a repeating
train/train/train/validation/test pattern dealt across the strata, which yields
an exact 60/20/20 split on 100 invoices.

Usage: python scripts/make_split_manifest.py [--seed N]
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "kaggle" / "Batch 1" / "batch_1.csv"
OUT_PATH = ROOT / "data" / "split_manifest.json"
DATASET = "devp1866/high-quality-ocr-ready-invoice-pdfs"
PATTERN = ("train", "train", "train", "validation", "test")


def load_item_counts() -> dict[str, tuple[str, int]]:
    """Map invoice_no -> (filename, number of line items)."""
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts = {}
    for row in rows:
        data = json.loads(row["json_data"])
        counts[data["invoice_no"]] = (row["filename"], len(data["items"]))
    return counts


def build(seed: int) -> dict:
    counts = load_item_counts()
    strata = defaultdict(list)
    for invoice_no, (_, n_items) in sorted(counts.items()):
        strata[n_items].append(invoice_no)
    rng = random.Random(seed)
    ordered = []
    for n_items in sorted(strata):
        group = strata[n_items]
        rng.shuffle(group)
        ordered.extend(group)
    sets = {name: [] for name in ("train", "validation", "test")}
    for index, invoice_no in enumerate(ordered):
        sets[PATTERN[index % len(PATTERN)]].append(invoice_no)
    return {
        "dataset": DATASET,
        "seed": seed,
        "method": "stratified by line-item count, 60/20/20",
        "sizes": {name: len(ids) for name, ids in sets.items()},
        "item_count_by_set": {
            name: {str(k): sum(1 for i in ids if counts[i][1] == k) for k in sorted(strata)}
            for name, ids in sets.items()
        },
        "sets": {
            name: [{"invoice_no": i, "filename": counts[i][0]} for i in sorted(ids)]
            for name, ids in sets.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    manifest = build(args.seed)
    OUT_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(ROOT)}: {manifest['sizes']}")


if __name__ == "__main__":
    main()

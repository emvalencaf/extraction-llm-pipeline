# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Render the regression-gate report of `data/baseline.json` into the README.

Usage:
    uv run scripts/gate_report.py           # rewrite the block between the markers in README.md
    uv run scripts/gate_report.py --check   # exit 1 if the README block is stale (CI-safe)
    uv run scripts/gate_report.py --stdout  # print the report only

The report is derived from the committed baseline only (no Gemini, no dataset), so the README
cannot drift from the accepted result.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = "<!-- gate-report:start -->"
END = "<!-- gate-report:end -->"


def render(baseline: dict) -> str:
    documents, correct = baseline["documents"], baseline["all_correct"]
    lines = [
        f"All-correct documents: **{correct}/{documents}** "
        f"(floor {baseline['floor']:.0%}, tolerated drop {baseline['max_regression']}, "
        f"prompt version `{baseline.get('prompt_version') or 'unknown'}`).",
        "",
        "| Field | Score |",
        "|---|---|",
        *(f"| {name} | {score:.4f} |" for name, score in sorted(baseline["field_scores"].items())),
    ]
    return "\n".join(lines)


def splice(readme: str, report: str) -> str:
    start, end = readme.find(START), readme.find(END)
    if start == -1 or end < start:
        raise SystemExit(f"README.md needs the {START} and {END} markers")
    return f"{readme[: start + len(START)]}\n{report}\n{readme[end:]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/baseline.json")
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)

    report = render(json.loads(args.baseline.read_text(encoding="utf-8")))
    if args.stdout:
        print(report)
        return 0
    current = args.readme.read_text(encoding="utf-8")
    updated = splice(current, report)
    if args.check:
        if updated != current:
            print("README gate report is stale; run `make gate-report`", file=sys.stderr)
            return 1
        return 0
    args.readme.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Required assayer changes

The regression gate ([scripts/regression_gate.py](../scripts/regression_gate.py)) uses
`assayer` (`llm-assayer-eval` 0.1.1) **unchanged**. This is the list of changes that
would let assayer carry more of the gate. None is implemented here and none blocks the
gate: each row says how the gate works around the gap today. Source: the assayer review
in `docs/research/assayer-interface-and-gaps.md` (branch `research/assayer-gaps`, issue #6).

| # | Change in assayer | Why the invoice gate needs it | Workaround in this repo |
|---|---|---|---|
| 1 | Numeric metric with relative tolerance that parses amount strings ("1,234.50", "INR 1,676,976.00") and rounds | `numeric_tolerance` is absolute and accepts numbers only | `adapters/assayer_scoring.py` normalizes both sides through the Extraction Schema and compares floats within 0.005 |
| 2 | Date metric that parses formats and compares as dates | Labels use dd/mm/yyyy, the pipeline emits ISO dates | Both sides are normalized to ISO strings, then `exact_match` |
| 3 | Gate and report module: thresholds, per-field minimums, regression-vs-baseline verdict, JSON and Markdown serialization of `Experiment` and `Comparison`, a headless CLI, and a per-document "all required fields correct" score | assayer returns raw deltas only and its experiments cannot be persisted | `domain/gate.py` decides the verdict and renders the report; `data/baseline.json` stores the per-field means |

Other gaps found in the review and left out of the three (they have workarounds that cost
nothing): currency as an amount-plus-code pair (G3), id and tax-id normalization hooks
(G4), `ListField` best-match mispairing on numeric items (G5, avoided with positional
alignment), union and nullable fields in schema drafting (G7), expected-null semantics
(G8) and judge rate limiting (G12, no judge is used).

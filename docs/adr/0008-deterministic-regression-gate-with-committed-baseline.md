# Deterministic regression gate with a committed baseline

The gate runs the real graph in-process in CI on the Test Set, scoring with
assayer's deterministic per-field metrics against ground truth; there are no LLM
judges, since ground truth exists and judges are non-deterministic and spend
quota. It fails when the all-fields-correct rate, any field's accuracy or the
`failed_validation` rate worsens by more than one document against the baseline,
and a persistent 429 gives the verdict *inconclusive*, which also fails. The
baseline (`data/baseline.json`) is committed and never rewritten by CI, so a
regression passes only by committing a lowered baseline that a reviewer can see.

The gate uses its own Gemini key from a separate Google project, so production
and smoke-test quota are not shared, and it runs only when a change touches
extraction-affecting paths.

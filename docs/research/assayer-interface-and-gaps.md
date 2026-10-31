# Research: assayer interface and gaps for invoice extraction eval

Issue: emvalencaf/extraction-llm-pipeline#6 (parent map #1).
Source: local checkout of `assayer` at commit `3b633c8` (package `llm-assayer-eval` 0.1.1,
import name `assayer`). Paths below are relative to the assayer repo root. assayer was read,
not modified. Claims cite the file that owns them.

## 1. Public API (what the gate can consume as-is)

Import from subpackages (`assayer/__init__.py` exports nothing):
`assayer.models`, `assayer.metrics`, `assayer.runner`, `assayer.registries`, `assayer.judges`,
`assayer.adapters`, `assayer.integrations`.

- `Dataset` / `Case(input, id, expected_output, ...)`: a Dataset is a list of Cases, a list of
  dicts, or a JSON file path (`assayer/runner/case_loader.py`). Only `input` plus the Case fields
  the chosen metrics `require` are mandatory; unknown keys are rejected; Case ids must be unique.
- `Runner(target, metrics, repetitions, pricing, field_metrics, adapter)` (`assayer/runner/runner.py`)
  - `run(dataset)` calls `target(case.input)`; an exception becomes an `error` on a model Step, not
    an abort.
  - `score(dataset, outputs)` scores outputs collected beforehand, without calling the target. This
    is the natural CI entry point: the pipeline produces extractions, assayer only scores them.
  - `export(experiment)` sends to the configured Adapter.
- `Experiment` (`assayer/models/experiment.py`): `trajectories`, `scores`, `failures`, `cases`,
  token usage and cost (`total_usage()`), judge usage kept separate, `scores_by_field()`.
- `Score` (`assayer/models/score.py`): `name`, `value` in [0, 1] (bools map to 0/1), `field`
  (dotted path), `comment`, `metadata`, `target`.
- `compare(experiment_a, experiment_b)` (`assayer/runner/compare.py`) returns a `Comparison`:
  `metric_deltas[(metric, field)] = mean_b - mean_a` (None if scored on one side only), token and
  cost deltas per Case, `only_in_a` / `only_in_b`.
- `Metric(name, level, fn, requires, kind)` (`assayer/metrics/metric.py`): custom metrics are a plain
  function `fn(subject, case) -> float | bool | Detailed | None`; a `Registry`
  (`assayer/registries/registry.py`) holds built-in and custom ones. Extending needs no core edit.

## 2. Structured-output / entity-extraction evaluation

The relevant mechanism is the **field map**, not only NER
(`.wiki/architecture/field-measurement.md`, `assayer/runner/field_map/`).

- `Runner(field_metrics={"dotted.path": [metric, (metric, params)], ...})` scores each output field
  on its own. The metric sees the field value as `final_output` and the expected value as
  `expected_output`; each Score carries `field`. Paths walk nested dicts; numeric segments index
  lists (`items.0.amount`). A field missing from the prediction arrives as `None`; missing from the
  Case becomes an `EvaluationFailure`.
- `ListField(properties={...}, align="best_match"|"key"|"positional", key=..., threshold=0.5)`
  aligns a list of objects (line items) and scores matched pairs property by property
  (`assayer/runner/field_map/list_field.py`, `scoring.py`, `assayer/alignment.py`). It emits
  `list_precision`, `list_recall`, `list_f1` for the list and per-property means (`items.name`);
  `metadata["alignment"]` lists pairs, `unmatched_expected` (missing) and `unmatched_predicted`
  (extra). Nested lists recurse. Best-match is greedy by similarity (mean of the pair's property
  scores), ties broken by position.
- `schema_to_field_map(schema_or_pydantic_model)` drafts a field map from a JSON Schema / Pydantic
  model; `to_yaml()` / `to_json()` write it out; `load_field_map(path)` / `parse_field_map(data)`
  read `.json` / `.yaml` (YAML needs the `yaml` extra) (`assayer/runner/field_map/schema.py`,
  `loader.py`). A field map can therefore be derived from the invoice extraction schema and
  committed as a reviewed file. Type defaults: number -> `numeric_tolerance` (tolerance 0), short
  string -> `normalized_exact_match`, other string -> `rouge_l`, enum/bool -> `exact_match` + `f1`,
  array of objects -> `best_match` list field. Unions of several types or unresolved `$ref` raise.
- `ner_macro_f1` and `NERMatcher` (`assayer/metrics/ner.py`, `ner_matching.py`) are span-based
  (text, type, start, end must all match). They do not apply to JSON field extraction.
- `examples/schema_structured_output.py` is a working end-to-end example close to the invoice
  use case (customer, order_total, list of items).

## 3. Deterministic metrics available

Field level (`assayer/metrics/field.py`): `exact_match`, `normalized_exact_match` (casefold +
whitespace collapse, strings only), `numeric_tolerance` (absolute difference <= tolerance; booleans
and non-numbers score 0), `list_f1` (order-insensitive, equality-based).
Corpus level (`assayer/metrics/corpus.py`, via `corpus_metric`): `accuracy`, `precision`, `recall`,
`f1` (macro), `bleu`, `rouge_l`, `bert_score`, `semantic_similarity`, `ner_macro_f1`. Per-field
corpus metrics see only that field's values. Also: consistency / `pass^k` / `score_std`
(`assayer/metrics/consistency.py`), agent and retrieval metrics (not relevant here).
Core install needs only `numpy` and `scikit-learn`; `bleu`/`rouge_l` need the `text` extra and
BERTScore/semantic need `torch` + HF model downloads (heavy; avoid in CI).

## 4. Judges

`Judge` is a provider-neutral Protocol with `complete(messages, schema=None) -> JudgeResponse`
(`assayer/judges/judge.py`); `LangChainJudge` wraps a langchain-core chat model (`langchain` extra;
`assayer/judges/langchain_judge.py`). Judge metrics: `make_criteria_judge` (1-5 scale normalised to
[0, 1], one retry on unparsable reply, then an `EvaluationFailure`, never a 0),
`make_goal_success`, `make_faithfulness` (`assayer/metrics/judge.py`). Judge tokens/calls are
accounted separately on the Experiment. For invoice extraction a Judge is optional: all fields have
ground truth, so deterministic metrics should carry the gate. A Judge could cover fuzzy fields
(vendor name variants), but it adds cost, rate limits and nondeterminism to a gate.

## 5. LangSmith coupling

Loose. LangSmith is an optional extra (`langsmith`) and only enters through `LangSmithAdapter`
(`assayer/integrations/langsmith_adapter.py`), used only by `Runner.export`. Scoring has no
LangSmith dependency. The adapter reads `LANGSMITH_API_KEY` (or `LANGCHAIN_API_KEY`) from the
environment, creates a dataset from the Cases, an experiment project, run trees per Trajectory and
Scores as feedback. A Langfuse adapter exists too, and `InMemoryAdapter` for tests. Export
failures are returned in an `ExportReport` (`ok`, `failed`, `skipped`), not raised. Exporting is
therefore optional for the gate and can be a post-step for tracing.

## 6. Output and report formats

There is **no built-in report**: no CLI, no `__main__`, no console script, no
JSON/JUnit/Markdown serializer for `Experiment` or `Comparison` (grep of `assayer/` for
`asdict|to_json|to_dict|argparse|__main__|console_scripts` finds only field-map drafting and judge
prompt helpers). Results are Python dataclasses; the only exports are to LangSmith/Langfuse.

## 7. Running headless in CI and gating on thresholds

Feasible today as a thin consumer script written in this repo, not as a built-in feature:

1. `pip install llm-assayer-eval[yaml]` (core + pyyaml; skip `semantic`/`text` extras if unused).
2. Load a committed ground-truth Dataset and a field map (`load_field_map`).
3. `Runner(field_metrics=...).score(dataset, outputs)` with the pipeline's outputs (no network,
   no LangSmith).
4. Aggregate in the script: per-field means from `experiment.scores_by_field()`, and
   `compare(baseline, candidate)` for deltas against a stored baseline.
5. Evaluate thresholds in the script; print a Markdown report; exit non-zero on breach; post the
   report as a PR comment.

What assayer does not provide for this: threshold/gate semantics (only `Comparison` deltas, no
pass/fail), a persisted baseline (Experiments are not serializable, so the baseline would have to
be stored as the script's own JSON of per-field means or re-scored from stored outputs), and
statistical significance for small sample sizes. `repetitions` plus consistency metrics can
quantify LLM nondeterminism before choosing thresholds.

## 8. Gaps for invoice field extraction (candidate "required assayer changes")

| # | Gap | Evidence | Workaround today |
|---|-----|----------|------------------|
| G1 | Numeric match is absolute tolerance only; no relative tolerance, no parsing of strings such as "1,234.50" / "R$ 1.234,50", no rounding | `numeric_tolerance` in `metrics/field.py` | Normalize in the pipeline output, or a custom `Metric` |
| G2 | No date metric (parse, normalise formats, compare as dates) | absent in `metrics/field.py`; dates would hit `normalized_exact_match` | Emit ISO-8601 in the schema; custom `Metric` |
| G3 | No currency/amount metric (code + amount pair, minor units, symbol handling) | absent | Split into `amount` and `currency` fields; `numeric_tolerance` + `exact_match` |
| G4 | No normalization hooks for ids / tax ids / strings beyond casefold+whitespace (punctuation, accents, "INV-001" vs "INV001") | `_normalize` in `metrics/field.py` | Custom `Metric` |
| G5 | `ListField` best-match similarity is the mean of the pair's property scores with a default 0.5 threshold; line items with mostly-numeric properties can mis-pair | `runner/field_map/scoring.py`, `alignment.py` | `align="key"` if items have an id; tune `threshold` |
| G6 | `list_f1` matches items by exact equality, so a list of objects scores 0 on any small difference | `list_f1` in `metrics/field.py` | Use `ListField` for objects |
| G7 | Schema drafting: union types / unresolved `$ref` raise; nullable fields (`["string","null"]`) are unions; strings longer than 64 chars default to `rouge_l` (fuzzy) | `runner/field_map/schema.py` | Hand-edit the draft; avoid unions |
| G8 | Null/absent semantics not distinguished: expected `null` ("field not on invoice") becomes an `EvaluationFailure` via `requires` (to verify per case) | `Metric.requires` in `metrics/metric.py` | Sentinel values or custom metric |
| G9 | No gating: no thresholds, no pass/fail, no per-field minimums, no regression-vs-baseline verdict, no significance | `compare.py` returns raw deltas only | Script in this repo |
| G10 | No serialization of `Experiment` / `Comparison` (JSON), no Markdown or JUnit report, no CLI | section 6 | Script in this repo |
| G11 | Aggregation is a plain mean over Cases per (metric, field); no per-document "all required fields correct" score, no field weighting | `compare._mean_scores` | Script in this repo |
| G12 | Judge is synchronous and sequential; no batching or rate-limit handling | `Judge.complete` is sync | Do not use a Judge in the gate |

G1-G4 and G8 are the strongest candidates for "required assayer changes" (new deterministic field
metrics or normalizer hooks). G9-G11 are candidates for a headless gate (a report/gate module and
a CLI); they could also stay in this repo as a thin script, which keeps assayer unmodified as the
map requires.

## 9. Open items to verify when implementing

- Confirm the Kaggle dataset's ground-truth shape maps onto the extraction schema.
- Confirm G8 behaviour with a test (nullable/absent expected values).
- Measure scoring time of the gate with core dependencies only.

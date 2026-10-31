# Free guardrails and NLP anonymization for invoice PII

Issue: #16 (parent map #1). Researched 2026-10-31 from first-party sources
(project repos, official docs, vendor docs). Facts only; no recommendations.
Items marked **Measured** were run locally (see "Local measurement"); items
marked **Inference** are reasoning from the cited facts, not from a source.

## Open gaps

- No first-party source publishes cold-start time or installed size for any of
  these libraries on Lambda. Only the local measurement below exists; it is not
  a Lambda number (WSL2, x86_64, Python 3.12).
- No first-party source covers how Gemini (or any LLM) treats `[REDACTED_X_1]`
  style placeholders in structured-output extraction. Needs a live test.
- Presidio accuracy on Indian invoice text is not published; the only accuracy
  figures found are spaCy generic NER scores (below).

## Candidates at a glance

| Library | License | Status (GitHub API, 2026-10-31) | Reversible anonymization built in |
|---|---|---|---|
| Microsoft Presidio (analyzer + anonymizer 2.2.366) | MIT | active, pushed 2026-10-29 | encrypt/decrypt only; placeholders via a custom-operator sample |
| LLM Guard (0.3.16) | MIT | **archived**, last push 2026-07-08 | yes: `Anonymize` + `Vault` + `Deanonymize` |
| Guardrails AI (0.11.0) | Apache-2.0 | active | no stated reversibility; `DetectPII` wraps Presidio |
| NeMo Guardrails (0.25.0-rc1) | Apache-2.0 | active | no stated reversibility; masking via Presidio or GLiNER-PII |

Sources: [Presidio repo](https://github.com/microsoft/presidio) (API reports
`data-privacy-stack/presidio`, MIT),
[presidio-analyzer pyproject](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/pyproject.toml),
[LLM Guard repo](https://github.com/protectai/llm-guard),
[LLM Guard pyproject](https://github.com/protectai/llm-guard/blob/main/pyproject.toml),
[Guardrails AI pyproject](https://github.com/guardrails-ai/guardrails/blob/main/pyproject.toml),
[NeMo Guardrails pyproject](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/pyproject.toml),
[NeMo LICENSE](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/LICENSE.md).
GitHub reported the NeMo repo license as `NOASSERTION` ("Other"); the LICENSE
file itself is Apache-2.0.

## Microsoft Presidio

### Packaging

- Python `>=3.11,<3.15`. Core deps of analyzer: spacy, numpy, regex, tldextract,
  phonenumbers, pydantic, pyyaml, click. Anonymizer core dep: `cryptography`
  only. Optional extras: `transformers`, `stanza`, `gliner` (gliner,
  onnxruntime, transformers), `langextract`, `server`.
  [analyzer pyproject](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/pyproject.toml),
  [anonymizer pyproject](https://github.com/microsoft/presidio/blob/main/presidio-anonymizer/pyproject.toml)
- Docs moved to https://presidio.dataprivacystack.org/ (old microsoft.github.io
  URLs redirect).
- Default NLP model is spaCy `en_core_web_lg`. Any spaCy model can be set per
  language via `NlpEngineProvider`; one NER model per language.
  [nlp models](https://presidio.dataprivacystack.org/analyzer/customizing_nlp_models/),
  [default.yaml](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/conf/default.yaml)
- spaCy model sizes and generic NER scores (not invoice-specific):
  `en_core_web_sm` 12 MB, ents F 0.843 (PERSON F 0.880, ORG 0.805, GPE 0.904);
  `en_core_web_lg` 382 MB, ents F 0.855. Both MIT.
  [sm meta](https://github.com/explosion/spacy-models/blob/master/meta/en_core_web_sm-3.8.0.json),
  [lg meta](https://github.com/explosion/spacy-models/blob/master/meta/en_core_web_lg-3.8.0.json)

### Recognizers relevant to Indian invoices

Source: [supported entities](https://presidio.dataprivacystack.org/supported_entities/)
and recognizer source under
`presidio-analyzer/presidio_analyzer/predefined_recognizers/`.

| Entity | Method (docs) | What the code does |
|---|---|---|
| `IN_PAN` | pattern, context | Regexes with scores 0.5 / 0.1 / 0.01; context words "permanent account number", "pan"; no checksum. |
| `IN_GSTIN` | pattern, context, validation | Regexes 0.8 / 0.4 / 0.1; validates length 15, state code 01-37, embedded PAN layout, 14th char `Z`. The docs entity description says "checksum", but the code does **not** verify the check digit (15th char only checked as alphanumeric). |
| `IN_AADHAAR` | pattern, context, checksum | Regexes at score 0.01; passes only if Verhoeff check, 12 digits, first digit >= 2, not palindrome; context "aadhaar", "uidai". |
| `IN_VOTER`, `IN_PASSPORT`, `IN_VEHICLE_REGISTRATION` | pattern, context (+checksum for vehicle) | Not relevant to invoices. |
| `PHONE_NUMBER` | `phonenumbers` lib | Default regions include `IN`; fixed score 0.4 base, leniency 1. |
| `EMAIL_ADDRESS`, `URL`, `IBAN_CODE`, `CREDIT_CARD` | pattern + validation/checksum | Generic. |
| `PERSON`, `LOCATION`, `NRP`, `DATE_TIME` | spaCy NER mapping | Quality bounded by the spaCy model. |

No recognizer exists for INR amounts, IFSC codes or Indian bank account
numbers; the registry has `US_BANK_NUMBER` only. The `IN_*` recognizers have
`supported_language` `en`.

### Reversibility

Source: [anonymizer docs](https://presidio.dataprivacystack.org/anonymizer/),
[pseudonymization sample](https://presidio.dataprivacystack.org/samples/python/pseudonymization/)

- Operators: `replace` (default value is the entity type, e.g. `<PHONE_NUMBER>`,
  not numbered), `redact`, `hash`, `mask`, `encrypt`, `custom`, `keep`.
- The only built-in deanonymize operator is `decrypt` (for `encrypt`).
  `DeanonymizeEngine` works from `OperatorResult` items (`start`, `end`,
  `entity_type`, `text`, `operator`), i.e. character offsets into the
  anonymized text.
- The pseudonymization sample builds numbered placeholders
  (`<{entity_type}_{index}>`) with two custom operators sharing a caller-held
  mapping dict. Caveats stated there: not thread-safe; index order can differ
  from text order; values the analyzer misses are never mapped; secure storage
  of the mapping is not covered.
- **Inference:** offset-based `DeanonymizeEngine` cannot be applied to LLM
  output, because the LLM rewrites the text and offsets no longer match. Only a
  mapping-based string substitution fits the extraction flow (placeholder ->
  original after the model returns).

## LLM Guard (Protect AI)

Sources: [anonymize.py](https://github.com/protectai/llm-guard/blob/main/llm_guard/input_scanners/anonymize.py),
[deanonymize.py](https://github.com/protectai/llm-guard/blob/main/llm_guard/output_scanners/deanonymize.py),
[analyzer.py](https://github.com/protectai/llm-guard/blob/main/llm_guard/input_scanners/anonymize_helpers/analyzer.py),
[pyproject](https://github.com/protectai/llm-guard/blob/main/pyproject.toml).

- Repo is **archived** (GitHub API `archived: true`); license MIT.
- Closest to the required design: `Anonymize` replaces PII with
  `[REDACTED_{ENTITY_TYPE}_{index}]`, e.g. `[REDACTED_PERSON_1]`, reusing the
  index for identical values, and stores `(placeholder, original)` pairs in a
  `Vault`. `Deanonymize(vault)` restores them in the LLM output.
- `Deanonymize` matching strategies: `EXACT` (default, plain substring),
  `CASE_INSENSITIVE`, `FUZZY` (`fuzzysearch`, max Levenshtein distance 3, not
  configurable through the scanner), `COMBINED_EXACT_FUZZY`. With `EXACT`, a
  placeholder altered by the LLM stays unrestored; fuzzy can replace look-alike
  text by mistake.
- Default recognizer config is a DeBERTa (AI4Privacy v2) transformer plus
  Presidio regex recognizers; `use_onnx` optional. Languages accepted: `en`,
  `zh`. Default entity types include `CREDIT_CARD`, `EMAIL_ADDRESS`, `PERSON`,
  `PHONE_NUMBER`, `US_SSN`, `IP_ADDRESS`, `UUID`; no `IN_*` types by default
  (custom regex patterns can be added via `regex_patterns`).
- Heavy deps: pins `torch>=2.4.0`, `transformers==4.51.3`,
  `presidio-analyzer==2.2.358`, Python `>=3.10,<3.13`. Exact pins and an
  archived repo constrain compatibility with newer Presidio.

## Guardrails AI

Sources: [pyproject](https://github.com/guardrails-ai/guardrails/blob/main/pyproject.toml),
[detect_pii README](https://github.com/guardrails-ai/detect_pii).

- Apache-2.0, Python `>=3.10,<3.14`. Core deps are large for Lambda:
  `litellm`, `openai`, `langchain-core`, `opentelemetry-*`, `faker`, `lxml`,
  `tiktoken`, `pydantic`.
- PII is a Hub validator, `DetectPII`, built on Presidio (`presidio-analyzer`,
  `presidio-anonymizer`). `on_fail` options include `fix` (anonymize),
  `exception`, `reask`, `filter`, `noop`. The README does not state whether the
  anonymization is reversible. The standalone repo is archived; the validator
  lives in the Guardrails Hub monorepo.
- Primary role is output validation/re-asking against schemas, not placeholder
  restoration.

## NeMo Guardrails (NVIDIA)

Sources: [pyproject](https://github.com/NVIDIA-NeMo/Guardrails/blob/develop/pyproject.toml),
[Presidio integration](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog/third-party/presidio),
[PII detection](https://docs.nvidia.com/nemo/guardrails/latest/configure-guardrails/guardrail-catalog/pii-detection).

- Apache-2.0, Python `>=3.10,<3.14`, version `0.25.0-rc1` (release candidate).
  Core deps include `fastembed`, `onnxruntime`, `numpy`, `aiohttp`, `jinja2`,
  `lark`; the `sdd` extra adds Presidio (Python `<3.13`).
- Sensitive-data rails run on input, output and retrieval: `detect` flows make
  the bot refuse; `mask` flows redact and continue. Docs require the
  `en_core_web_lg` spaCy model. `score_threshold` default 0.2.
- Other PII options in the docs: GLiNER-PII via NVIDIA NIM (hosted needs an
  `NVIDIA_API_KEY`; local Docker needs an NGC key) and Private AI (API key).
  Masking uses label placeholders (`[FIRST_NAME]`); reversibility is not
  stated. Pricing and model sizes are not stated.
- Built around a conversational `LLMRails` runtime; using it in a LangGraph
  extraction pipeline means running its engine as an extra layer
  (**Inference**).

## Other technique notes

- Regex + checksum recognizers (no ML): Presidio's `IN_AADHAAR` (Verhoeff) and
  `IN_GSTIN` structural validation are plain Python under
  `predefined_recognizers/country_specific/india/` and can be reused as
  reference logic.
- GLiNER is available as a Presidio extra (`gliner`, `onnxruntime`); model
  sizes and Indian-invoice accuracy were not found in first-party docs.

## Lambda constraints

Source: [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)

- Zip: 50 MB zipped (direct upload; larger via S3), **250 MB unzipped**
  including layers. Container image: 10 GB uncompressed. 5 layers max.
- Memory 128-10,240 MB (1 vCPU at 1,769 MB); timeout 900 s; `/tmp` 512-10,240 MB.

## Gemini free-tier data terms (why anonymize)

From the sibling note `docs/research/gemini-free-tier.md` (branch
`research/gemini-free-tier`, sourced from
[Gemini API terms](https://ai.google.dev/gemini-api/terms)): on the free tier,
prompts and responses may be used to improve Google products and read by human
reviewers, and Google says not to submit sensitive or personal information.

## Local measurement (Measured)

Environment: WSL2, Linux x86_64, Python 3.12.3, uv venv, `presidio-analyzer`
and `presidio-anonymizer` 2.2.366, spaCy 3.8.18, numpy 2.4.6. One synthetic
invoice text (GSTIN, PAN, Aadhaar, Indian phone, email, INR total, bank
account, IFSC). Single runs, not a benchmark.

- Installed `site-packages`: **316 MB** without a model, **331 MB** with
  `en_core_web_sm` (largest: spacy 121 MB, blis 39, numpy 30 + numpy.libs 28,
  phonenumbers 23, thinc 15, cryptography 15). This exceeds the 250 MB unzipped
  zip limit before adding LangGraph or the Gemini client.
- Start-up: import `presidio_analyzer` 5.2 s on the first run (cold disk
  cache), 0.88 s on rerun; building the engine with `en_core_web_sm`
  0.38-0.45 s; first `analyze` 0.19-0.64 s; warm `analyze` 0.015 s; peak RSS
  170 MB.
- The default `AnalyzerEngine` registry did **not** include any `IN_*`
  recognizer (loaded: CREDIT_CARD, CRYPTO, DATE_TIME, EMAIL_ADDRESS, IBAN_CODE,
  IP_ADDRESS, MAC_ADDRESS, MEDICAL_LICENSE, PHONE_NUMBER, UK_NHS, URL,
  US_BANK_NUMBER, US_DRIVER_LICENSE, US_ITIN, US_PASSPORT, US_SSN, UUID).
  `IN_PAN`, `IN_GSTIN`, `IN_AADHAAR` had to be added with
  `registry.add_recognizer(...)`.
- With them added: `IN_GSTIN` 1.0 (`29ABCDE1234F1Z5`), `IN_AADHAAR` 1.0
  (`2345 6789 0124`), `IN_PAN` 0.45 (`ABCDE1234F`) plus a 0.01 false positive
  on `-2024-0042` (invoice number fragment). `PHONE_NUMBER` 0.75
  (`+91 98765 43210`), `EMAIL_ADDRESS` 1.0, `PERSON` `Priya Nair` 0.85.
- False positives with `en_core_web_sm` and default recognizers: `PERSON` for
  `Aadhaar` and for `ABCDE1234F\nBill` (span crossing a line); `ORGANIZATION`
  for `PAN`, `INR`, `IFSC`, `Bank A/C`; `DATE_TIME` for `560001`,
  `98765 43210`, `123456789012`, `2345 6789 0124`; `URL` split of the email.
  Overlapping results need conflict resolution before substitution.
- Not detected as PII: seller business name (Sharma Traders Pvt Ltd), IFSC
  `HDFC0001234`, bank account `123456789012` (only low-score `US_BANK_NUMBER`
  0.4 and `DATE_TIME`).

## Placeholder round trip through an LLM

- First-party evidence is limited to the LLM Guard code above: exact-match
  restoration fails if the model alters the placeholder; fuzzy matching
  (distance 3) is offered as mitigation with a stated false-positive risk.
- Presidio's sample documents the mapping-state requirements: one mapping per
  document, same value -> same placeholder, caller-held and not thread-safe.
- **Inference (unverified):** a per-invocation mapping kept in Lambda memory
  (never sent to the LLM) is sufficient because extraction runs within one
  invocation; placeholders returned inside JSON string fields can be restored
  by string substitution `placeholder -> original`. Whether Gemini preserves
  bracketed placeholders verbatim in structured output, and how often it
  normalizes or drops them, needs a test against the real model with the
  synthetic Kaggle invoices.

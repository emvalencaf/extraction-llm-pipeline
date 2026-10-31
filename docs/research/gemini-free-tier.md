# Gemini API free tier: capabilities and limits

Issue: #3 (parent map #1). Researched 2026-10-31 from first-party Google AI docs only.
Facts only; no recommendations.

## Open gap

Per-model free-tier numeric limits (RPM, TPM, RPD) are NOT published in the
docs. The rate-limits page says limits vary by model and tier and are shown only
in AI Studio (https://aistudio.google.com/rate-limit, login required). They must
be read there by a human with the project's account before gating decisions.
[rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)

## Models on the free tier

Source: [pricing](https://ai.google.dev/gemini-api/docs/pricing) (free-tier column).

- Free tier available, text/multimodal generation (stable unless noted):
  `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`,
  `gemini-3.1-flash-lite`, `gemini-3-flash-preview` (preview),
  `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, Gemma 4.
- Also free: live/transcribe/TTS models, `gemini-embedding-001`,
  `gemini-embedding-2`, robotics-ER previews.
- NOT free: `gemini-4-argon`, `gemini-3.1-pro-preview`, image/Omni/Lyria models.
- Status ([models](https://ai.google.dev/gemini-api/docs/models),
  [deprecations](https://ai.google.dev/gemini-api/docs/deprecations)): the 2.5
  models are not deprecated and have no shutdown date, but access is limited to
  users who have used them before; docs recommend `gemini-3.5-flash-lite` or
  `gemini-3.8-flash` for new projects. `gemini-2.0-flash*` shutdown was June 1,
  2026 (past). `gemini-3.1-flash-lite-preview` shutdown May 25, 2026 (past).
- Preview and experimental models have stricter limits.

## Rate limit mechanics

Source: [rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)

- Dimensions: RPM, input TPM, RPD (some models TPD, image models IPM).
  Exceeding any single one triggers an error.
- Limits are per project, not per API key. RPD resets at midnight Pacific.
- Limits are not guaranteed; actual capacity may vary.
- Built-in tools have separate limits (e.g. Search grounding on Gemini 3+:
  1,500 RPD per project by default).
- Tiers: Free (active project), Tier 1 (billing linked), Tier 2 ($100 cumulative
  + 3 days), Tier 3 ($1,000 cumulative + 30 days). Free to Tier 1 is usually
  instant.
- Batch API: 100 concurrent jobs, 2 GB input file, 20 GB storage; enqueued-token
  caps are listed only for Tier 1 and up (no free-tier column).

## Input limits

- PDF ([document-processing](https://ai.google.dev/gemini-api/docs/document-processing)):
  50 MB or 1000 pages per PDF (pages also combined across PDFs in a request);
  258 tokens per page; the 50 MB limit applies to inline and File API; File API
  retention 48 hours, File API is free. Only PDFs get full vision; TXT/HTML/etc.
  are read as plain text.
- Images ([image-understanding](https://ai.google.dev/gemini-api/docs/image-understanding)):
  up to 3,600 images per request; inline data counts toward a 20 MB total
  request limit (use File API beyond); PNG, JPEG, WEBP, HEIC, HEIF; 258 tokens
  for images <=384 px, else 768x768 tiles at 258 tokens each; Gemini 3 has a
  `media_resolution` parameter to cap tokens.
- Context ([gemini-3.8-flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
  [gemini-3.5-flash-lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)):
  1,048,576 input tokens, 65,536 output tokens, inputs text/image/video/audio/PDF,
  structured outputs supported. Not checked for 3.6-flash, 3.1-flash-lite or the
  2.5 models (their model pages were not fetched).

## Structured output (JSON schema)

Source: [structured-output](https://ai.google.dev/gemini-api/docs/structured-output)

- Request with mime type `application/json` plus a schema (JSON Schema, Pydantic
  or Zod). Examples use `gemini-3.8-flash`.
- Supported: string, number, integer, boolean, object, array, null; `enum`,
  `format` (date-time, date, time), `minimum`/`maximum`, `minItems`/`maxItems`,
  `prefixItems`, `required`, `additionalProperties`, `title`, `description`.
- Silently ignored (no error): `minLength`, `maxLength`, `minProperties`,
  `maxProperties`, `uniqueItems`, `contains`, `minContains`, `maxContains`.
  Validate these client-side.
- Large or deeply nested schemas can return `400 INVALID_ARGUMENT` (too many
  states / too much branching).
- Schema-valid output can still be semantically wrong.
- Structured output combined with tools is a preview feature, Gemini 3 only.
- Newer models (Gemini 4, 3.6+) reject `temperature`, `top_p`, `top_k` with 400
  per [troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting).

## Data usage

Source: [terms](https://ai.google.dev/gemini-api/terms),
[pricing](https://ai.google.dev/gemini-api/docs/pricing)

- Free (unpaid) tier: prompts and responses are used to improve Google products
  and ML; human reviewers may read them (disconnected from account/key/project).
  Google says not to submit sensitive, confidential or personal information.
- Paid (project with active billing): not used for training; logged for a
  limited time for abuse/safety/legal; governed by the Data Processing Addendum.
- EEA, Switzerland, UK: paid-service data terms apply even to free usage, and
  API clients serving users there may use only Paid Services.
- Search/Maps grounding: prompts and outputs stored 30 days regardless.

## Errors and retry semantics

Sources: [api-errors](https://ai.google.dev/gemini-api/docs/api-errors),
[troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)

| HTTP | Code | Action |
|---|---|---|
| 400 | invalid_request, failed_precondition, parameter_unknown | Do not retry unchanged; fix request (precondition e.g. billing) |
| 403 | permission_denied | Do not retry; key/tier/billing/leaked key; new key in same project does not fix free-tier restriction |
| 404 | not_found, model_not_found | Fix model name or path |
| 429 | rate_limit_exceeded (per-minute/second) | Retry with exponential backoff and jitter, capped retries |
| 429 | quota_exceeded (daily) | Wait for reset (midnight Pacific for RPD) or raise tier |
| 429 | too_many_requests | Slow down, exponential backoff |
| 500 | api_error | Retry; contact support if persistent |
| 503 | service_unavailable | Retry with exponential backoff and jitter |
| 504 | deadline_exceeded | Raise or remove client deadline |

- Docs do not mention a `Retry-After` header or RetryInfo detail fields.
- 429 RESOURCE_EXHAUSTED is also used for spend-based limits (paid tiers).
- Python SDK retries 429 automatically.
- Errors arrive as an `error` object with `code` and `message`; streaming sends
  the same in an SSE event.

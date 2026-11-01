# Invoice Extraction Pipeline

A pipeline that turns invoice PDFs into structured, validated data using an LLM, and gates every change against a measured regression baseline.

## Language

**Invoice**:
A PDF document requesting payment, issued by a seller to a client.
_Avoid_: Bill, document (when the invoice specifically is meant)

**Seller**:
The party that issues the invoice.
_Avoid_: Vendor, supplier

**Client**:
The party the invoice is addressed to.
_Avoid_: Buyer, customer

**Line Item**:
One row of an invoice: a described product or service with quantity, unit, unit price, net amount, VAT percentage and gross amount.
_Avoid_: Row, product line

**Extraction**:
The structured record the pipeline produces from one invoice, conforming to the Extraction Schema.
_Avoid_: Parse result, output

**Extraction Schema**:
The single definition of the fields of an Extraction, from which the model's tool schema and the client-side validation are both derived.
_Avoid_: Model, format

**Ground Truth**:
The human-verified expected Extraction of an invoice, after normalization of the source labels.
_Avoid_: Labels (once normalized), answer key

**Normalization**:
The conversion of raw values (formatted strings, local date formats, currency prefixes) into the canonical types of the Extraction Schema.
_Avoid_: Cleaning, formatting

**Inconsistent Extraction**:
An Extraction whose amounts do not reconcile arithmetically (line items versus totals, VAT versus net).
_Avoid_: Invalid extraction, bad extraction

## Dataset splits

**Train Set**:
The invoices that supply few-shot examples for the prompt and free exploration.

**Validation Set**:
The invoices used to tune prompts and choose models during development.

**Test Set**:
The invoices that feed the regression gate; their errors are never used to tune prompts.
_Avoid_: Golden set

**Split Manifest**:
The committed, seeded list of which invoice belongs to which set.

## Privacy

**Placeholder**:
A stable token that replaces a sensitive value before the model sees the invoice, and is swapped back after extraction.
_Avoid_: Mask, redaction

**Anonymization**:
The replacement of an invoice's sensitive values (names, addresses, tax ids, contact and bank details) with Placeholders before the model sees the text. Amounts, dates, invoice number, currency and line item descriptions are not sensitive here.
_Avoid_: Redaction, scrubbing

**Restore**:
The swap of each Placeholder in a validated Extraction back to its original value. A Placeholder that is missing, altered or left over makes the Extraction invalid.
_Avoid_: Deanonymization, unmasking

**Leak Rate**:
The share of invoices where at least one Ground Truth sensitive value still appears in the text after Anonymization.
_Avoid_: Miss rate

## Grounding

**Grounding Rate**:
The share of checked field values of an Extraction that appear in the invoice's own text. Measured per job and aggregated per run; it says a value is present in the source, not that it is correct.
_Avoid_: Hallucination rate, accuracy

**Ungrounded Value**:
An extracted value, among those checked, that cannot be found in the invoice's text.
_Avoid_: Hallucination, wrong value

## Jobs

**Job**:
One request to extract one invoice, tracked from creation to a final status and returned to the client by id.
_Avoid_: Task, request

**Job Status**:
The state of a Job: awaiting_upload, queued, processing, succeeded, failed_validation, failed or expired. It changes only through allowed transitions, enforced by conditional writes.
_Avoid_: Phase, stage

**Idempotency Key**:
An optional client-chosen value on job creation; repeating it returns the same Job instead of creating another.
_Avoid_: Request id, dedupe token

**Retry Policy**:
The queue rules for an infrastructure failure: the maximum number of receives, and a visibility delay that doubles per receive up to a cap. On the last receive the Job is marked failed.
_Avoid_: Backoff config

**Redrive**:
The replay of messages from the dead-letter queue back to the main queue after an outage is fixed. Only Jobs that failed after exhausting their receives are replayed.
_Avoid_: Retry, requeue

**Wide Event**:
One structured JSON log line that carries the whole context of an operation, either an `llm_call` (one model call) or a `job` (one Job end to end). It never contains invoice content.
_Avoid_: Log line, trace

## Prompts

**Prompt Bundle**:
The single versioned unit holding everything that shapes the model's behavior: the system prompt, the few-shot examples, the repair prompt and the model settings. The few-shot examples are anonymized with Placeholders, like real inputs.
_Avoid_: Prompt (when the whole unit is meant), template

**Prompt Version**:
The content-derived identifier of a Prompt Bundle; any change to the bundle yields a new one.
_Avoid_: Prompt release, tag

**Baseline**:
The committed Test Set scores of the currently deployed Prompt Bundle, against which a candidate is compared.
_Avoid_: Golden result, snapshot

## Regression gate

**Regression Gate**:
The check that scores a candidate on the Test Set and compares it with the Baseline, ending in one verdict: passed, failed or inconclusive.

**Inconclusive**:
The Regression Gate verdict when the run could not finish scoring the Test Set (for example, persistent rate limiting); it blocks like a failure.

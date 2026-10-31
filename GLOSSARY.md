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

# Research: Kaggle invoice dataset structure and ground truth

Issue: #2 (parent map: #1). Date of inspection: 2026-10-31.

Dataset: `devp1866/high-quality-ocr-ready-invoice-pdfs`
(https://www.kaggle.com/datasets/devp1866/high-quality-ocr-ready-invoice-pdfs),
"High-Quality OCR-Ready Invoice PDFs", version 1 (the only version).

## Method and sources

- **Dataset files**: downloaded the dataset zip from the Kaggle public API
  (`GET https://www.kaggle.com/api/v1/datasets/download/devp1866/high-quality-ocr-ready-invoice-pdfs`,
  no credentials needed) into an empty directory outside the repo. The files were
  treated as untrusted data and read only by scripts run with `python -I`
  (stdlib `csv`/`json`, plus `pypdf` 6.21.4 for PDF inspection). Nothing from the
  dataset is committed here.
- **Dataset metadata** (license, owner, version, size, description): Kaggle public
  API, `GET https://www.kaggle.com/api/v1/datasets/view/devp1866/high-quality-ocr-ready-invoice-pdfs`.
- Every number below was computed from the downloaded files, not copied from the
  dataset description, unless marked "(description)".

## Verdict for the decisions that wait on this

- The dataset is **fully synthetic and template-generated**: one seller, one
  layout, one font pair, one page size, one currency, one tax rate. It is good for
  a smoke test and for schema design, but it is **not representative of real
  invoices**. It cannot, alone, validate layout/vendor robustness.
- All 100 PDFs have a **real embedded text layer** and no images. No OCR is needed,
  and no scanned-document path is exercised.
- The ground truth is **internally consistent** (all arithmetic reconciles, see
  below) and has 100% file-to-label coverage. It has a few format quirks that the
  schema must normalise (strings for every number, thousands separators, `INR`
  prefix, dd/mm/yyyy dates, a stray newline in 7 values).

## License and provenance

| Fact | Value | Source |
|---|---|---|
| License | Apache 2.0 | Kaggle API `licenseName` |
| Owner | DEVKUMAR PATEL (`devp1866`) | Kaggle API |
| Versions | 1 ("Initial release", 2026-05-20) | Kaggle API `versions` |
| Origin | Fully synthetic; generated with ReportLab, text extracted with pdfplumber (description) | Kaggle API `description`; PDF `/Producer` is `ReportLab PDF Library - (opensource)` (confirmed in files) |
| Real data | None; names, numbers, prices are random (description) | Kaggle API `description` |

Apache 2.0 permits use, modification and redistribution with notice. Because the
data is synthetic there is no PII concern. Do not commit the dataset to the repo
regardless (project instruction); keep it as a downloaded fixture.

## File layout, count and size

```
Batch 1/
  batch_1.csv                  307,606 bytes
  invoices/invoice_51109301.pdf ... invoice_51109400.pdf   (100 files)
```

- Zip: 101 entries, 308,758 bytes compressed, 665,387 bytes uncompressed
  (matches Kaggle `totalBytes`).
- PDFs: 100, 3,050 to 4,061 bytes each, 357,781 bytes total. No duplicate files.
- Filename is `invoice_<invoice_no>.pdf`; invoice numbers are the contiguous
  range 51109301 to 51109400, all unique. Filename and `invoice_no` agree in 100/100.
- The description shows `invoices/` and `batch_1.csv` at the root; the real archive
  nests them under `Batch 1/` (the name implies future batches, but only one exists).

## Ground-truth format

`batch_1.csv`: UTF-8, 100 rows, header `filename,json_data,ocred_text`.
`filename` matches the PDFs 1:1 (no missing, no orphan, no duplicate rows).
`json_data` parses as JSON in 100/100 rows. `ocred_text` is the pdfplumber text of
the PDF (description); it is not byte-equal to a pypdf extraction because the
two extractors order the two-column Seller/Client block differently.

### Fields in `json_data` (same shape in every row)

```
invoice_no        str   "51109301"
date_of_issue     str   "03/07/2023"          dd/mm/yyyy
seller{name,address,tax_id,gstin}
client{name,address,tax_id}
items[]{item_no,description,quantity,unit_measure,net_price,net_worth,vat_pct,gross_worth}
summary{vat_pct,net_worth,vat_amount,gross_worth,total_net_worth,total_vat,total_gross_worth}
```

- **Every value is a string**, including quantities and money
  (`"74,120.00"`, `"10%"`, `"9.00"`). Item numbers carry a trailing dot (`"1."`).
- Money has thousands separators (western grouping, e.g. `1,676,976.00`, not
  Indian lakh grouping) and two decimals. The currency is only present in the
  summary, as a prefix (`"INR 1,844,673.60"`) on the `total_*` fields.
- `summary` is redundant: `net_worth`/`vat_amount`/`gross_worth` (bare numbers) and
  `total_net_worth`/`total_vat`/`total_gross_worth` (same numbers prefixed with
  `INR `). The prefixed form equals `"INR " + bare` in 100/100 rows.
- The description's field list is incomplete: it omits `unit_measure`, item-level
  `net_worth`, and the bare summary fields.
- Items per invoice: 1 to 8 (counts 1:12, 2:8, 3:11, 4:19, 5:14, 6:14, 7:12, 8:10),
  455 items total. Single page per invoice, so no multi-page tables.

## Native text versus scanned

- 100/100 PDFs: 1 page, A4 (595.28 x 841.89 pt), **0 embedded images**, fonts
  `Helvetica` and `Helvetica-Bold` only, non-empty extractable text.
- Therefore: **no scanned or image-only PDFs**, no handwriting, no skew, no noise,
  no stamps or logos. Any OCR/vision path (needed for real-world inputs) is
  untested by this data; it would need to be simulated (rasterise and degrade) or
  sourced elsewhere.
- Text extraction quirks the pipeline will meet even on native text:
  - Long descriptions wrap onto a second line inside the cell, so the extracted
    text splits a description around the Qty/UM/price columns. This affects 80 of
    455 items (e.g. "Apple Watch Series 9 GPS 45mm" / "Midnight"). The label has the
    joined string.
  - The summary line "INR 167,697.60" (VAT) wraps as "INR" then the number.
  - The header cell "Gross Worth" wraps across two lines.
  - Seller and Client are laid out side by side in the rendered page, so a
    left-to-right extractor (pdfplumber) interleaves the two blocks.

## Layout and vendor variety

- **One layout.** The PDFs differ only in data. One seller (TechVision
  Distributors Pvt Ltd, identical name/address/tax_id/gstin in 100/100), 50 unique
  buyers (each appears exactly twice, one address each), 19 Indian states/UTs in
  addresses, 40 distinct product descriptions (descriptions repeat across
  invoices), one unit (`pcs`), one VAT rate (`10%` in 455/455 items and 100/100
  summaries), one currency (INR).
- Dates: all valid dd/mm/yyyy, range 2023-04-11 to 2024-04-05. In 45 of 100
  invoices the day is <= 12, so the date is ambiguous with mm/dd unless the format
  is specified; the other 55 are unambiguous dd/mm.
- No variation in field order, labels, language, currency, tax regime, line-item
  count of columns, discounts, shipping, notes, payment terms, due dates, PO
  numbers or bank details. Fields a real extraction schema often needs and that
  are absent here: due date, currency per document, payment terms, discounts,
  per-line tax codes (HSN), buyer GSTIN, CGST/SGST/IGST split.

## Label quality checks

Checked on all 100 rows:

| Check | Result |
|---|---|
| `json_data` valid JSON | 100/100 |
| Filename equals `invoice_<invoice_no>.pdf` | 100/100 |
| Item `net_worth` = quantity x net_price | 455/455 |
| Item `gross_worth` = net_worth x 1.10 (within 0.01) | 455/455 |
| Sum of item net_worth = summary net_worth | 100/100 |
| Sum of item gross_worth = summary gross_worth (within 0.02) | 100/100 |
| summary vat_amount = 10% of net_worth | 100/100 |
| invoice number, date, client name, totals appear in the PDF text | 100/100 |
| Seller `tax_id` equals seller `gstin` | 100/100 (redundant, not distinct fields) |

Defects and oddities found:

1. **Embedded newline in 7 item `gross_worth` values** (e.g. `"1,101,523.5\n0"` in
   invoices 51109337, 51109338, 51109340, 51109360, 51109362, 51109381, 51109397). The label copied
   the PDF cell wrap into the string. Naively parsing as a number fails; the
   golden set should either fix these or the comparison must strip whitespace.
   This is the only malformed value class found.
2. **Client `tax_id` has US SSN format** (`999-99-9999` in 100/100, e.g.
   `901-95-4704`), not an Indian PAN/GSTIN. It is a synthetic-generator artefact;
   do not treat it as a realistic identifier or validate it as a GSTIN.
3. **Seller `tax_id` and `gstin` are the same constant** (`27AABCT1234F1Z5`), so
   this dataset cannot test distinguishing the two.
4. **Redundant summary fields** (see above): decide which is canonical; scoring
   both would double count.
5. **All numerics are strings with formatting**; the schema must define a
   normalisation (decimal type, strip `,` and `INR`, `%`).
6. **Cell-wrapped descriptions** are joined in the label but split in text
   (above); an extractor that returns the first line only would be marked wrong.
7. No missing, empty or null fields were found in any row. Because of that, the
   dataset has no negative examples (absent fields, `null` handling).

## Implications for the schema and golden set

- A schema covering this data is small: invoice_no, date (parse as dd/mm/yyyy),
  seller, client, items (description, quantity, unit, unit price, net, tax %,
  gross), totals, currency. Decide on decimals instead of strings, and make
  currency a document-level field (it is only a prefix on totals here).
- Golden set: the labels are usable almost as-is for deterministic comparison, since
  arithmetic is exact. Needed cleanup: strip the 7 newlines, drop the redundant
  summary fields, and normalise numbers/dates. 100 invoices from one template give
  high count but low diversity; treat it as one "easy native-text" stratum, not a
  representative sample.
- To test what the project will actually face, the golden set needs additional
  sources for: scanned/image PDFs, multiple vendors and layouts, other currencies
  and tax regimes, multi-page tables, and missing/optional fields.
- Suggested scoring caveat: because every invoice shares one seller and one VAT
  rate, seller and VAT accuracy will look perfect for a model that memorises them;
  weight buyer, items and totals.

## Unverified

- The Kaggle web page itself (rendered view, discussion, the 2 linked notebooks)
  was not inspected; license and description came from the API.
- No claim is made about the "Batch 1" naming implying later batches; only
  version 1 exists as of 2026-10-31.

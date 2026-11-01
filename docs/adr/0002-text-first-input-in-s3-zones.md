# Text-first input, staged in S3 zones

The model receives the text layer of the PDF, never the native PDF. The upload
lands in the `raw/` zone, `load_input` writes the extracted text to `processed/`
under a key derived from `job_id` (a redelivery overwrites it idempotently), and
the SQS message carries only the S3 key. Anonymization needs text, and scanned
PDFs with no text layer are a deliberate, documented limitation: they end as
`failed_validation` (`no_text_layer`), with no OCR.

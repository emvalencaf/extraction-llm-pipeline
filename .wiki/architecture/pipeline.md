---
type: Service
title: Invoice extraction pipeline
description: Async API, SQS worker and LangGraph graph that turns an invoice PDF into a validated Extraction.
resource: src/invoice_extraction
tags: [architecture, pipeline]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: package
    resource: src/invoice_extraction
    title: invoice_extraction package
---

# Overview

`POST /jobs` returns a presigned upload URL; the PDF lands in S3, an event goes to
SQS, and a Lambda worker runs the graph (load input, anonymize, extract,
validate, repair, restore, finalize) and writes the job to DynamoDB.

Key decisions: [hexagonal layout](/decisions/0001-hexagonal-package-and-container-images.md),
[text-first input](/decisions/0002-text-first-input-in-s3-zones.md),
[anonymization](/decisions/0003-reversible-anonymization-with-presidio.md),
[presigned upload](/decisions/0005-presigned-upload-and-s3-events-straight-to-sqs.md),
[regression gate](/decisions/0008-deterministic-regression-gate-with-committed-baseline.md).

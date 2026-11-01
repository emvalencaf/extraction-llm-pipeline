---
type: Decision
title: "Presigned S3 upload, with S3 events going straight to SQS"
description: "`POST /jobs` returns a presigned PUT URL and the client uploads the PDF to `raw/{job_id}.pdf`, so the 10 MB and 29 s API Gateway limits never apply to the document."
resource: docs/adr/0005-presigned-upload-and-s3-events-straight-to-sqs.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0005-presigned-upload-and-s3-events-straight-to-sqs.md
    title: 0005-presigned-upload-and-s3-events-straight-to-sqs
---

# Decision

Presigned S3 upload, with S3 events going straight to SQS. The full record is the ADR at `docs/adr/0005-presigned-upload-and-s3-events-straight-to-sqs.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

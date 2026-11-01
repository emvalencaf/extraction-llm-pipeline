---
type: Decision
title: "Local stack from per-service emulators, with a fake Gemini"
description: "The local stack uses the Lambda RIE with the real image, DynamoDB Local, a moto S3 server and ElasticMQ for the queues, with a home-made poller reproducing the decided SQS contract and a thin FastAPI shim standing in for API Gateway."
resource: docs/adr/0012-local-stack-emulators-and-fake-gemini.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0012-local-stack-emulators-and-fake-gemini.md
    title: 0012-local-stack-emulators-and-fake-gemini
---

# Decision

Local stack from per-service emulators, with a fake Gemini. The full record is the ADR at `docs/adr/0012-local-stack-emulators-and-fake-gemini.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

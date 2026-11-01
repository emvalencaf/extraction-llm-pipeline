---
type: Decision
title: "Business failures are terminal; the DLQ is for infrastructure only"
description: "When validation still fails after repair and escalation, or the PDF has no text layer, the job ends as `failed_validation` with its reason and best attempt, and the SQS message is consumed."
resource: docs/adr/0004-business-failures-are-terminal-dlq-is-for-infrastructure.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0004-business-failures-are-terminal-dlq-is-for-infrastructure.md
    title: 0004-business-failures-are-terminal-dlq-is-for-infrastructure
---

# Decision

Business failures are terminal; the DLQ is for infrastructure only. The full record is the ADR at `docs/adr/0004-business-failures-are-terminal-dlq-is-for-infrastructure.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

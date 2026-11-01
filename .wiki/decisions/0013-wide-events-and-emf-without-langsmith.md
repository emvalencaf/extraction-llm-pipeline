---
type: Decision
title: "Wide events with embedded metrics; no LangSmith"
description: "Observability is two JSON wide events joined by `job_id` (`llm_call` and `job`), with CloudWatch metrics embedded as EMF rather than metric filters or `PutMetricData`, and no extra dimensions so the metrics stay inside the 10 free custom me"
resource: docs/adr/0013-wide-events-and-emf-without-langsmith.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0013-wide-events-and-emf-without-langsmith.md
    title: 0013-wide-events-and-emf-without-langsmith
---

# Decision

Wide events with embedded metrics; no LangSmith. The full record is the ADR at `docs/adr/0013-wide-events-and-emf-without-langsmith.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

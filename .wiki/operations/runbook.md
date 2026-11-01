---
type: Playbook
title: Alarm runbook
description: One entry per CloudWatch alarm of the observability module, plus redrive and key rotation.
resource: docs/runbook.md
tags: [operations, alarms, runbook]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: runbook
    resource: docs/runbook.md
    title: docs/runbook.md
---

# Overview

Every alarm publishes to the single SNS `alerts` topic. The source of truth is
`docs/runbook.md`; read it for the per-alarm steps. Design rationale is in
[wide events and EMF](/decisions/0013-wide-events-and-emf-without-langsmith.md)
and [business failures are terminal](/decisions/0004-business-failures-are-terminal-dlq-is-for-infrastructure.md).

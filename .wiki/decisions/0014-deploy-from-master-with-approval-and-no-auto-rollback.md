---
type: Decision
title: "Deploy from `master` behind approval; rollback is a revert"
description: "`deploy.yml` runs on push to `master` - gate (only if extraction paths changed since the last successful deployment), `terraform plan`, approval on the `production` Environment, apply of the approved plan, then a smoke test."
resource: docs/adr/0014-deploy-from-master-with-approval-and-no-auto-rollback.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0014-deploy-from-master-with-approval-and-no-auto-rollback.md
    title: 0014-deploy-from-master-with-approval-and-no-auto-rollback
---

# Decision

Deploy from `master` behind approval; rollback is a revert. The full record is the ADR at `docs/adr/0014-deploy-from-master-with-approval-and-no-auto-rollback.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

---
type: Decision
title: "Terraform state, bootstrap and full teardown"
description: "`infra/bootstrap/` (local state, run once by hand) creates the state bucket and this repository's CI roles; everything else is composed from `infra/modules/` with S3 native locking (`use_lockfile`, Terraform 1.10 or later) and its own state"
resource: docs/adr/0010-terraform-state-bootstrap-and-teardown.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0010-terraform-state-bootstrap-and-teardown.md
    title: 0010-terraform-state-bootstrap-and-teardown
---

# Decision

Terraform state, bootstrap and full teardown. The full record is the ADR at `docs/adr/0010-terraform-state-bootstrap-and-teardown.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

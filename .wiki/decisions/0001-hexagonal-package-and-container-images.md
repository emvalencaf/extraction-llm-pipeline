---
type: Decision
title: "Hexagonal package, shipped as container images"
description: "All code lives in one package, `src/invoice_extraction/`, split into `domain/`, `application/`, `adapters/`, `composition/` and `entrypoints/`, with imports pointing inward only and enforced by import-linter."
resource: docs/adr/0001-hexagonal-package-and-container-images.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0001-hexagonal-package-and-container-images.md
    title: 0001-hexagonal-package-and-container-images
---

# Decision

Hexagonal package, shipped as container images. The full record is the ADR at `docs/adr/0001-hexagonal-package-and-container-images.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

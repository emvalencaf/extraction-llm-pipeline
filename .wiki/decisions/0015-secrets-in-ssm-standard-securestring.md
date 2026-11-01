---
type: Decision
title: "Secrets in SSM Standard SecureString"
description: "The production Gemini key and the API key live in SSM SecureString parameters of the Standard tier, encrypted with the AWS-managed `aws/ssm` key, which is free."
resource: docs/adr/0015-secrets-in-ssm-standard-securestring.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0015-secrets-in-ssm-standard-securestring.md
    title: 0015-secrets-in-ssm-standard-securestring
---

# Decision

Secrets in SSM Standard SecureString. The full record is the ADR at `docs/adr/0015-secrets-in-ssm-standard-securestring.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

---
type: Decision
title: "Native API Gateway key, 403 on a bad key, single-tenant access"
description: "The API is a REST API (HTTP APIs have no API keys) with a native key on a usage plan, so API Gateway rejects bad calls before any Lambda runs - 1 request/s, burst 2 and 100 `POST /jobs` a day, sized for the 500 requests/day Gemini quota."
resource: docs/adr/0011-native-api-gateway-key-and-single-tenant-access.md
tags: [adr, decisions]
status: stable
generated: { by: process:publish-wiki, at: 2026-11-01T00:00:00Z }
sources:
  - id: adr
    resource: docs/adr/0011-native-api-gateway-key-and-single-tenant-access.md
    title: 0011-native-api-gateway-key-and-single-tenant-access
---

# Decision

Native API Gateway key, 403 on a bad key, single-tenant access. The full record is the ADR at `docs/adr/0011-native-api-gateway-key-and-single-tenant-access.md`; this concept exists so the
decision shows up in the knowledge graph. Related: [all decisions](index.md).

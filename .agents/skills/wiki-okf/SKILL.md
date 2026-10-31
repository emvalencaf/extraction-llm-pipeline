---
name: wiki-okf
description: >-
  Shared Open Knowledge Format (OKF) rules for the wiki-okf-* skills: the hard
  conformance rule, file conventions, the default `.wiki/` location, the
  verbatim v0.2 spec and the concept, index and log templates. Not invoked
  directly; wiki-okf-produce, wiki-okf-maintain and wiki-okf-consume point here.
user-invocable: false
allowed-tools: Read
metadata:
  source: https://github.com/scaccogatto/okf-skills
  derived-from: okf
---

# Open Knowledge Format (OKF) core

OKF represents knowledge as a directory of markdown files with YAML frontmatter.
It is minimal by design: no schema registry, no runtime, no SDK. Produce,
maintain and consume bundles **conformant with the spec**, not your memory of it.

## The one hard rule

A bundle is conformant (§11) iff: every non-reserved `.md` file has a parseable
YAML frontmatter block, and every such block has a **non-empty `type`** field.
Everything else is soft guidance. Consumers MUST tolerate missing optional
fields, unknown types, and broken links; never reject a bundle over them.

## Conventions

- **One concept = one file.** The file path (minus `.md`) is the concept ID.
- **Frontmatter:** `type` is required. Add `title`, `description`, `tags` when
  they aid consumption; add `resource` (a canonical URI) only for concepts bound
  to a real asset; omit it for abstract concepts.
- **Body:** prefer structural markdown (headings, tables, lists, fenced code).
  Conventional headings: `# Schema`, `# Examples`, `# Computation`.
- **Cross-links:** standard markdown links; prefer absolute bundle-relative
  form (`/services/auth-api.md`). A link asserts a relationship; its *kind*
  lives in the surrounding prose, not the link.
- **Reserved files:** `index.md` (directory listing, no frontmatter, except the
  bundle-root index, which may carry `okf_version` and this project's
  `upkeep: enforced` opt-in flag) and `log.md` (ISO-dated change history,
  newest first). Never use these names for concepts.

## Default bundle location

Use `.wiki/` at the repository root unless the project already uses another
location. Commit it alongside the code it describes: knowledge as code.

## Files

- [references/SPEC.md](references/SPEC.md): the verbatim OKF v0.2 specification
  and the source of truth for every rule. Read it before non-trivial work.
- [references/v0.2-families.md](references/v0.2-families.md): trust, lifecycle,
  provenance and attestation fields, plus how to read a v0.1 bundle. Read it
  before writing frontmatter.
- [assets/concept.md](assets/concept.md), [assets/index.md](assets/index.md),
  [assets/log.md](assets/log.md): templates to copy.
- [references/APACHE-2.0.txt](references/APACHE-2.0.txt): license of the spec.

## Skills that use this

- `wiki-okf-produce`: create or extend a bundle.
- `wiki-okf-maintain`: keep a bundle in sync with code and docs.
- `wiki-okf-consume`: use a bundle as context.
- `wiki-okf-query`, `wiki-okf-validate`, `wiki-okf-visualize`,
  `wiki-okf-backfill`: search, check, graph and reconstruct a bundle.

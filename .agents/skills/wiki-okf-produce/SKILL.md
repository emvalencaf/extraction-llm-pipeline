---
name: wiki-okf-produce
description: >-
  Create or extend an Open Knowledge Format (OKF) knowledge bundle from code,
  docs or manual input, scaffolding a new one with `okf_init.py`. Use when
  capturing project knowledge (services, APIs, schemas, metrics, runbooks,
  decisions) into a bundle, or on "document this in OKF", "capture this as a
  concept", "create a knowledge bundle". To sync an existing bundle after a
  change, use wiki-okf-maintain.
user-invocable: true
argument-hint: "[path]"
allowed-tools: Read Write Edit Grep Glob Bash
metadata:
  source: https://github.com/scaccogatto/okf-skills
  derived-from: okf (produce mode)
---

# Produce an OKF bundle

Read [../wiki-okf/SKILL.md](../wiki-okf/SKILL.md) for the conformance rule and
conventions, and [../wiki-okf/references/v0.2-families.md](../wiki-okf/references/v0.2-families.md)
before writing frontmatter. Default target is `.wiki/` at the repository root.

## New bundle

Scaffold it instead of hand-writing the first files. It writes a conformant
`index.md`, `log.md` and a `getting-started.md` concept with the full
recommended frontmatter:

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/okf_init.py" <target-dir> [--title "..."]
```

It refuses a directory that already has `.md` files unless `--force` is given.

## Extend a bundle

1. Read [../wiki-okf/references/SPEC.md](../wiki-okf/references/SPEC.md).
2. Pick the source(s): **code** (derive concepts from source, READMEs,
   docstrings, config), **docs/wiki** (distill pages into concepts, record the
   originals in `sources`), **manual** (decisions, playbooks, metrics).
3. Choose a directory layout by domain (e.g. `services/`, `datasets/`,
   `decisions/`). One concept per file.
4. Write each concept from
   [../wiki-okf/assets/concept.md](../wiki-okf/assets/concept.md): set a
   descriptive `type`, fill the recommended fields, record `generated` and the
   `sources` you actually read, cross-link related concepts.
5. Add or refresh `index.md` per directory (from
   [../wiki-okf/assets/index.md](../wiki-okf/assets/index.md)) and
   `okf_version: "0.2"` in the root index. Append a dated entry to `log.md`.
6. Validate with `wiki-okf-validate <bundle-dir> --strict`. Fix every error and
   warning before finishing.

For a repository that already has history, `wiki-okf-backfill` can reconstruct
the bundle instead.

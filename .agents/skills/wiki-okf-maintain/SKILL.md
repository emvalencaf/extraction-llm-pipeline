---
name: wiki-okf-maintain
description: >-
  Keep an Open Knowledge Format (OKF) bundle in sync with reality after code or
  docs change: update affected concepts, deprecate removed assets, refresh
  indexes and the log. Use on "update the knowledge bundle", "sync the wiki",
  after a code or docs change in a repo with a `.wiki/` bundle, or when the
  pre-commit hook asks for it. To create a bundle, use wiki-okf-produce.
user-invocable: true
argument-hint: "[path]"
allowed-tools: Read Write Edit Grep Glob Bash
metadata:
  source: https://github.com/scaccogatto/okf-skills
  derived-from: okf (maintain mode)
---

# Maintain an OKF bundle

Read [../wiki-okf/SKILL.md](../wiki-okf/SKILL.md) for the conformance rule and
conventions, and [../wiki-okf/references/v0.2-families.md](../wiki-okf/references/v0.2-families.md)
before writing frontmatter. Default target is `.wiki/` at the repository root.

1. Identify which concepts the change affects (search by `resource`, path, or
   topic). This bookkeeping is exactly what agents are good at: touch every
   affected file in one pass.
2. Update the body and `generated.at`, with your own actor in `generated.by`.
   Fix or add cross-links. Create new concepts for new assets, copying
   [../wiki-okf/assets/concept.md](../wiki-okf/assets/concept.md).
3. Mark removed assets `status: deprecated` and note the deprecation in
   `log.md` instead of silently deleting context.
4. When you touch a v0.1 concept (`timestamp`, `# Citations`), migrate its
   frontmatter as part of the edit. For a whole v0.1 bundle, do not hand-edit:
   run `wiki-okf-validate --migrate` once.
5. Update the relevant `index.md` files and append a dated `log.md` entry
   describing what changed.
6. Validate with `wiki-okf-validate <bundle-dir> --strict`. Fix every error and
   warning before finishing.

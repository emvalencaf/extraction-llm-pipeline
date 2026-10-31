---
name: wiki-okf-consume
description: >-
  Rules for reading an Open Knowledge Format (OKF) bundle as context and
  deciding how far to trust it. Use whenever a repository contains a `.wiki/`
  (or other OKF) bundle that may inform the task, or on "what do we know about
  X". Covers progressive reading and trust signals; it delegates the search
  itself to wiki-okf-query.
user-invocable: true
argument-hint: "[path]"
allowed-tools: Read Grep Glob Bash
metadata:
  source: https://github.com/scaccogatto/okf-skills
  derived-from: okf (consume mode)
---

# Consume an OKF bundle

1. Read the bundle-root `index.md` first for progressive disclosure, then follow
   links only into the concepts relevant to the task. To find them from a
   question, use `wiki-okf-query` instead of scanning files.
2. Weigh what you read:
   - `status: draft` or `deprecated`: check before relying on it.
   - `stale_after` already past: check before relying on it.
   - No `verified` entry: nobody has confirmed it. A `by` starting with
     `human:` is the strongest signal; `process:` and agent actors are weaker.
   - Broken links are knowledge not yet written, not errors.
3. Need a number an `Attested Computation` concept covers? Run *its*
   computation with values bound to the declared `parameters`. Never write your
   own query.
4. If you learn something durable while working, switch to `wiki-okf-maintain`
   and write it back.

Field definitions are in
[../wiki-okf/references/v0.2-families.md](../wiki-okf/references/v0.2-families.md).

---
type: Skill
title: usage-report skill
description: Local HTML dashboard of Claude Code usage, including the session recaps Claude Code writes when you step away.
resource: .agents/skills/usage-report/SKILL.md
tags: [skills, usage-report, recaps]
status: stable
generated: { by: claude-code/pre-commit, at: 2026-10-11T00:00:00Z }
sources:
  - id: skill-md
    resource: .agents/skills/usage-report/SKILL.md
    title: usage-report SKILL.md
  - id: parser
    resource: .agents/skills/usage-report/scripts/usage_report.py
    title: Transcript parser (parse_session)
  - id: views
    resource: .agents/skills/usage-report/scripts/views.py
    title: HTML views (recap_row)
  - id: recap-tests
    resource: tests/test_usage_recaps.py
    title: Recap tests
---

# Overview

`usage-report` reads Claude Code transcripts for the project and writes a local
HTML dashboard (tokens, sessions, skills, tools, subagents, work grouping).[^skill-md]

# Session recaps

Claude Code writes a `system` entry with subtype `away_summary` when the user
steps away. The parser collects every one per session as `{ts, text}`, in
transcript order, and strips the trailing `(disable recaps in /config)` hint.
Empty recaps are dropped.[^parser]

- Shown verbatim, in the conversation's original language, never translated.
- Rendered by `recap_row` as a collapsed `<details>` row ("N recaps") under the
  session in the Sessions table and under each member session in the Work
  cards. Text is HTML-escaped; sessions without recaps render no row.[^views]
- Recaps are conversation text, so they widen the report's privacy surface
  beyond numbers, names and ids. Keep the report local; `.claude/usage/` is
  git-ignored.[^skill-md]
- Covered by `uv run --with pytest pytest tests`.[^recap-tests]

[^skill-md]: usage-report SKILL.md
[^parser]: Transcript parser (parse_session)
[^views]: HTML views (recap_row)
[^recap-tests]: Recap tests

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Entries are added
under `Unreleased` in the PR that makes the change, and moved under a dated
heading when `development` is released to `master`.

## [Unreleased]

### Added

- Split Manifest (seed 42, 60/20/20 stratified by line-item count) and its generator
  `scripts/make_split_manifest.py`.
- Live Gemini Placeholder preservation test and its write-up in
  `docs/experiments/gemini-placeholder-preservation.md` (140/140 verbatim on the
  Validation Set).
- `kaggle` (dev) and `google-genai` dependencies; `data/kaggle/` is git-ignored.
- `implement-spec` accepts an optional ticket range or list (e.g. `28-33`) to implement
  only a subset of a spec's tickets, leaving the spec and other tickets open.

## [0.2.0] - 2026-10-23

### Added

- `usage-report` shows the session recaps Claude Code writes when you step away:
  every recap of a session, verbatim, in the Sessions table and the Work cards.
  Adds `tests/test_usage_recaps.py` (`uv run --with pytest pytest tests`).

### Changed

- The `okf` skill is split by mode into `wiki-okf-produce`, `wiki-okf-maintain`
  and `wiki-okf-consume`; `wiki-okf` stays as a non-invocable core holding the
  conformance rule, conventions, `SPEC.md`, the v0.2 families reference and the
  templates. `okf_init.py` moved to `wiki-okf-produce`.
- `validate`, `visualize`, `query` and `backfill` renamed to `wiki-okf-validate`,
  `wiki-okf-visualize`, `wiki-okf-query` and `wiki-okf-backfill`. The `/okf`
  command no longer exists and has no alias. The pre-commit hook, CI,
  `ask-harness` and the README use the new names.
- These skills are now a local fork of
  [scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills), so their
  entries were removed from `skills-lock.json`.
- `ask-matt` and `setup-matt-pocock-skills` removed; `ask-harness` and
  `setup-project-harness` carry `metadata.source` and `metadata.derived-from`
  crediting them, as do the `wiki-okf-*` skills for `scaccogatto/okf-skills`.
- `README.md` restructured after
  [Best-README-Template](https://github.com/othneildrew/Best-README-Template).
- `setup-project-harness` now generates the project's own README from
  `README.template.md`, which follows the same structure.
- `CODE_STANDARDS.md` and `AGENTS.md`: documentation standard for READMEs.
- `setup-project-harness` synced with the updated `setup-matt-pocock-skills`:
  `GLOSSARY.md` / `GLOSSARY-MAP.md` replace `CONTEXT.md` / `CONTEXT-MAP.md`, the
  GitHub and GitLab tracker templates are refreshed, and missing triage labels
  are created on the tracker.
- `ask-harness` synced with `ask-matt`: `GLOSSARY.md` naming, plus `/prototype`,
  `/implement-spec`, `/pr`, `/retro` and `/teach`.
- Skills that told users to run `/setup-matt-pocock-skills` now point to
  `/setup-project-harness`.
- Every skill keeps supporting files in `scripts/`, `references/` and `assets/`
  instead of the skill root (`okf/reference` and `okf/templates` renamed to
  `references` and `assets`); `CODE_STANDARDS.md` documents the layout.

## [0.1.0] - 2026-09-20

First release of the project template.

### Added

- Template scaffolding: `README.md` with step-by-step instructions for using the
  template, `.gitignore`, `.editorconfig`, `pyproject.toml` (ruff), `.wiki/` OKF
  knowledge bundle, PR template and commit template.
- `CONTRIBUTING.md` (branch strategy and commit convention), `CODE_STANDARDS.md`
  and this changelog.
- Git hooks in `.githooks/`: `commit-msg` enforces the commit format;
  `pre-commit` checks Unicode, runs ruff, and updates `.wiki/` automatically
  (via `claude -p`, with one validator-guided retry) with strict validation.
  Skip the wiki update with `SKIP_WIKI_UPDATE=1`.
- Scripts: `scripts/setup.sh`, `scripts/protect-master.sh`,
  `scripts/check_unicode.py`, `scripts/set-budget.sh`,
  `scripts/usage-tracking.sh` and `scripts/usage_log.sh`.
- GitHub Actions CI (`.github/workflows/ci.yml`): PR target rule (only
  `development` may target `master`), Unicode, ruff, `.wiki/` validation and
  commit message format checks.
- Project-level status line (`.claude/settings.json` and `scripts/statusline.sh`)
  showing project, model, branch (dirty and ahead/behind markers, red on
  `master`/`main`/`development`), context, cost or budget, rate limits,
  duration and session id. `scripts/set-budget.sh` sets, shows or clears the USD
  budget used for pay-per-token accounts (project or `--global`).
- Per-session usage log: the status line writes `.claude/usage/<session>.json`
  (git-ignored) when enabled with `scripts/usage-tracking.sh on|off|status`.
- `query` skill: natural-language search over OKF bundles, with `--limit` and
  metadata filters (`--type`, `--tag`, `--status`, `--path`, `--generated-by`,
  `--verified-by`, `--resource`, `--source`, `--stale`/`--fresh`,
  `--verified`/`--unverified`, `--include-deprecated`).
- `usage-report` skill: local HTML dashboard with tabs (Overview, Work, By type,
  Sessions). Tokens in and out per day, session and skill, duration, model,
  effort, context peak, top skills, heuristic intents and tool usage (names,
  calls, errors, time). The Work tab groups sessions by spec, ticket, feature
  directory or branch across the grill, spec, tickets, implement and review
  flow, resolves local `.scratch/` files and GitHub issues, and links commits
  through the `Session-Id` trailer (`--tracker`, `--offline`). Subagents appear
  as separate rows linked to their session and are never added to its totals. The
  By type tab classifies work as feature, bug fix, refactor, etc. from commit
  tags, branch prefix, GitHub labels or the opening skill. The logged cost is
  always labelled an estimate.

### Changed

- Renamed `ask-matt` to `ask-harness` and extended it to route the OKF skills
  (`query`, `okf`, `validate`, `visualize`, `backfill`), `usage-report` and the
  repo workflow. Dropped the `/prototype` and `/teach` references, which are not
  in this repo.
- Renamed `setup-matt-pocock-skills` to `setup-project-harness`; it now also sets
  the project name and description, configures `CODE_STANDARDS.md` with the
  matching `pyproject.toml` settings, and asks whether to keep usage tracking on
  and, for pay-per-token users, the status line budget.
- Moved the knowledge bundle from `.okf/` to `.wiki/`.

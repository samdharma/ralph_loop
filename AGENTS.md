# AGENTS.md

This repository is managed by **Ralph v3**, an automated build system.

## Pipeline Overview

Ralph runs each ticket through a 3-stage pipeline:

1. **DESIGN** — Systems architect researches the codebase and writes a design spec in `docs/designs/<issue-number>.md` and structured artifacts in `.ralph/issues/<issue-number>/artifacts/`.
2. **BUILD** — Two sub-agents run in sequence:
   - **TEST** (isolated, fresh session) writes tests from the spec only.
   - **IMPLEMENT** (artifact-based handoff) reads the DESIGN artifacts and writes code to make the tests pass.
3. **VERIFY** — Independent reviewer (isolated, fresh session) reviews the diff against the issue and spec.

## Provider Error Handling (Kimi / Pi)

The orchestrator now detects provider-side failures from agent output:

- **Rate-limit / 429** — pauses the daemon for 15 minutes, reverts the current ticket to `status:ready`, and leaves all other ready tickets untouched.
- **Quota / billing limit** — tries the alternate agent once (e.g., Kimi → Pi). If the alternate agent also fails, Ralph creates a project issue documenting the exhaustion and stops gracefully.

Do NOT mark tickets `status:blocked` for provider errors.

## For Agents

- You have access to: **git**, **gh** (GitHub CLI), **python**, **pi**, **kimi**, and **bash**.
- Read `docs/agent/PROMPT.md` for universal rules and the failure-reporting contract.
- Read the stage prompt for your current role in `docs/agent/prompts/<stage>.md`.
- Read `docs/designs/<issue-number>.md` for the design spec and `.ralph/issues/<issue-number>/artifacts/` for the structured handoff artifacts.
- Follow existing code conventions. Research the codebase before writing.
- Run `ralph validate --tier=targeted` when your stage work is complete.
- Do NOT modify GitHub labels or issues **during pipeline execution** — the orchestrator handles all in-flight label transitions. After Ralph hands off (`status:review`), external review tools may update labels.

## Project Layout

```
src/                   → Application source
tests/unit/            → Unit tests
tests/integration/     → Integration tests
config/                → Project configuration
docs/                  → Documentation
logs/                  → Daemon logs (gitignored)
.ralph/                → Ralph state (gitignored)
```

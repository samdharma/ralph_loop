# Design Spec: Isolate Per-Issue Design Specs from `PROGRESS.md`

| | |
|---|---|
| **Status** | Draft (awaiting implementation) |
| **Author** | Sam Dharma (drafted with AI assistance) |
| **Target repo** | `samdharma/Ralph_loop` (this repo) |
| **Triggering incident** | gap_scanner #72 — TEST sub-agent received a 15,865-line `PROGRESS.md` containing designs for ~12 unrelated issues, exited non-zero, blocked the build. |
| **Related ralph fix** | `29b62b5 fix(engine): protect all run_pipeline/stage calls from provider errors` (different bug, same investigation) |

---

## 1. Summary

`docs/agent/PROGRESS.md` is currently used as a shared append-only log of every design spec the DESIGN stage has ever produced. After ~12 issues it is 15,865 lines long. The TEST and IMPLEMENT sub-agents receive the entire file as "the design spec" for their issue, with no demarcation of which slice is relevant. This causes:

- Confused sub-agents (the wrong spec is more visible than the right one)
- A `_summarize_design_spec()` that posts the title of the *first* H1 in the file, which is a stale design from a previous issue
- A growing token cost on every stage prompt
- An unbounded growth pattern — the same bug will recur on every project

**Fix:** Move per-issue design specs into `docs/designs/<issue-number>.md` (one file per issue, replaced — never appended — on each design pass). Demote `PROGRESS.md` to a small status board consumed by the engine and humans, not by sub-agents.

---

## 2. Goals

1. Each issue's design spec is isolated in its own file at `docs/designs/<N>.md`.
2. The TEST and IMPLEMENT sub-agents receive *only* the design for their issue, not a concatenated blob.
3. The design summary posted as a GitHub issue comment reflects the actual current issue, not a stale H1 from a previous design.
4. `PROGRESS.md` becomes a small status board (target: < 200 lines) that the engine can regenerate from `gh` + filesystem state.
5. No regression in the in-flight Mode B session inheritance — the `--continue --session` flow stays as-is.
6. The fix is backward compatible with projects that have already accumulated design content in `PROGRESS.md` (their historical content stays put, not deleted).

## 3. Non-Goals

- This doc does **not** change the DESIGN prompt's "Output Format" (the H1 `# Design Spec: #<N> <title>` structure stays).
- This doc does **not** introduce a new docs framework (no mkdocs, no sphinx, no design-doc tooling).
- This doc does **not** change the in-conversation Mode B inheritance mechanism.
- This doc does **not** touch `PROMPT.md` (the universal rules for agents) or the `prompts/test.md` / `prompts/implement.md` / `prompts/verify.md` files (only `prompts/design.md` and the engine change).
- This doc does **not** migrate existing in-PROGRESS.md content. Old design content stays in `PROGRESS.md` as historical artifact; new issues go to the new location.

---

## 4. Approach

### 4.1 New file layout

```
docs/
├── agent/                        ← ralph orchestration (consumed by engine)
│   ├── PROGRESS.md               ← small status board (target: < 200 lines)
│   ├── PROMPT.md                 ← universal agent prompt (unchanged)
│   ├── prompts/                  ← stage prompts
│   │   ├── design.md             ← UPDATED (writes to docs/designs/<N>.md)
│   │   ├── test.md               ← unchanged
│   │   ├── implement.md          ← unchanged
│   │   └── verify.md             ← unchanged
│   └── progress-isolation.md     ← this doc
└── designs/                      ← NEW: per-issue design specs (project content)
    ├── 70.md
    ├── 71.md
    ├── 72.md
    └── ...
```

Rationale for `docs/designs/` (not `docs/agent/designs/`):
- `docs/agent/` is ralph's working directory (prompts, queue). Private to the engine.
- `docs/designs/` is project documentation. Survives the build, browsable by humans, reviewable in PRs.
- The line is clean: agent/ is meta, designs/ is content.

### 4.2 New constants in `core/engine.py`

Add near line 36 (next to `PROGRESS_FILE`):

```python
# Per-issue design specs live in docs/designs/<N>.md (one file per issue).
# These are project content, separate from PROGRESS.md (the ralph queue).
DESIGN_SPEC_DIR = PROJECT_ROOT / "docs" / "designs"
PROGRESS_FILE = PROJECT_ROOT / "docs" / "agent" / "PROGRESS.md"  # unchanged
```

Add a small helper (place near other path helpers around line 144):

```python
def _design_spec_path(issue_num: int) -> Path:
    """Return the path to the per-issue design spec for issue_num."""
    return DESIGN_SPEC_DIR / f"{issue_num}.md"
```

### 4.3 Engine changes — exact line numbers

#### Change A: `_summarize_design_spec()` — `core/engine.py:1298`

**Before** (line 1299–1302): reads `PROGRESS_FILE` and parses the first H1.

**After:** read from the per-issue file. Fall back to `PROGRESS_FILE` only if the per-issue file does not exist (backward compat for projects mid-migration).

```python
def _summarize_design_spec(issue_num: int) -> Optional[str]:
    """Read the per-issue design spec and return a condensed summary
    for posting as a GitHub issue comment.

    Reads from docs/designs/<issue_num>.md (preferred).
    Falls back to docs/agent/PROGRESS.md if the per-issue file is missing
    (backward compat for projects mid-migration).
    """
    design_file = _design_spec_path(issue_num)
    if design_file.exists():
        text = design_file.read_text(encoding="utf-8")
    elif PROGRESS_FILE.exists():
        # Backward compat: legacy projects with content only in PROGRESS.md
        text = PROGRESS_FILE.read_text(encoding="utf-8")
    else:
        return None

    lines = text.splitlines()
    title = ""
    summary_parts: list[str] = []
    decisions: list[str] = []
    risks: list[str] = []
    ac_count = 0
    section: Optional[str] = None

    # ... existing parser unchanged ...

    out = ["## 📐 Design Complete", ""]
    out.append(f"**{title}**")
    # ... rest unchanged ...
    out.append("")
    out.append("Full design spec committed to `docs/designs/" + str(issue_num) + ".md`.")
    return "\n".join(out)
```

**Call site change:** the function is currently called with no arguments at `core/engine.py:623`. Change the call site to pass `issue_num`:

```python
# core/engine.py:623 — was: design_summary = _summarize_design_spec()
design_summary = _summarize_design_spec(issue_num)
```

#### Change B: `_read_partial_design_spec()` — `core/engine.py:1368`

**Before** (line 1369–1376): reads `PROGRESS_FILE` for the partial-design failure path.

**After:** read from the per-issue file, fall back to `PROGRESS_FILE` for backward compat:

```python
def _read_partial_design_spec(issue_num: int, max_chars: int = 2000) -> Optional[str]:
    """Read the per-issue design spec (or PROGRESS.md fallback) if it exists.
    Returns truncated content or None if neither file exists."""
    design_file = _design_spec_path(issue_num)
    text: Optional[str] = None
    if design_file.exists():
        text = design_file.read_text(encoding="utf-8")
    elif PROGRESS_FILE.exists():
        text = PROGRESS_FILE.read_text(encoding="utf-8")
    if text is None:
        return None
    try:
        text = text.strip()
        if not text:
            return None
        if len(text) > max_chars:
            text = (
                text[:max_chars].rstrip()
                + "\n\n_(truncated — see file for full content)_"
            )
        return text
    except OSError:
        return None
```

**Call site change:** the function is called at `core/engine.py:595` (in the DESIGN failure path):

```python
# core/engine.py:595 — was: partial_spec = _read_partial_design_spec()
partial_spec = _read_partial_design_spec(issue_num)
```

#### Change C: `_assemble_subagent_prompt()` — `core/engine.py:1558` (Mode A block)

**Before** (line 1558–1561):

```python
# Design spec (Mode A only — Mode B already has it in session context)
if mode == "A" and PROGRESS_FILE.exists():
    design_spec = PROGRESS_FILE.read_text(encoding="utf-8")
    prompt += f"\n\n## Design Spec (from DESIGN stage)\n\n{design_spec}"
```

**After:** inject the per-issue file in **both** Mode A and Mode B. (Mode B currently relies on the in-session context, but injecting the file makes the prompt robust against session loss and makes the prompt self-contained for the IMPLEMENT agent.)

```python
# Design spec — read per-issue file (preferred) with PROGRESS.md fallback.
# Injected in both Mode A and Mode B so the prompt is self-contained.
design_file = _design_spec_path(issue["number"])
if design_file.exists():
    design_spec = design_file.read_text(encoding="utf-8")
    prompt += (
        f"\n\n## Design Spec (from DESIGN stage)\n\n"
        f"{design_spec}\n\n"
        f"_Source: `docs/designs/{issue['number']}.md` — "
        f"this is the design for the current issue only._"
    )
elif PROGRESS_FILE.exists():
    # Backward compat: legacy projects with content only in PROGRESS.md
    design_spec = PROGRESS_FILE.read_text(encoding="utf-8")
    prompt += (
        f"\n\n## Design Spec (from DESIGN stage)\n\n"
        f"{design_spec}\n\n"
        f"_Source: `docs/agent/PROGRESS.md` (legacy location) — "
        f"may contain designs for other issues; use the section that "
        f"matches issue #{issue['number']}._"
    )
```

#### Change D: `commit_stage()` and the DESIGN commit message

**Verify** (no change required, but document for the implementer):

The DESIGN stage currently commits whatever the DESIGN agent wrote. After this change, the DESIGN agent writes to `docs/designs/<N>.md` (a new file) and *may* also touch `docs/agent/PROGRESS.md` (the status board). Both should be committed in the same DESIGN commit. The current `commit_stage()` function (`core/engine.py`) does `git add -A` and commits, so both files are picked up automatically. **No code change needed — but the implementer should verify by running one DESIGN end-to-end and inspecting the commit.**

### 4.4 Prompt change — `docs/agent/prompts/design.md`

Replace the "Your Goal" line (currently line 6):

**Before:**

```markdown
## Your Goal
Write a design spec in `docs/agent/PROGRESS.md` that the TEST and IMPLEMENT sub-agents can execute without further research.
```

**After:**

```markdown
## Your Goal
Write the design spec to `docs/designs/<issue-number>.md` so the TEST and IMPLEMENT sub-agents can execute it without further research.

Rules:
- Use the `write` tool with the path `docs/designs/<issue-number>.md`.
- **Replace** the file if it already exists. Do not append. Do not edit `docs/agent/PROGRESS.md` with design content — that file is a status board, not a design log.
- The H1 of the design file MUST be `# Design Spec: #<issue-number> <title>` exactly.
- After writing, use the `read` tool to verify the file contents.
- Use the Output Format below.
```

Also add a clarifying line in the "Constraints" section at the end of `prompts/design.md`:

```markdown
- Do NOT append to `docs/agent/PROGRESS.md`. The design lives in `docs/designs/<N>.md`.
- You MAY add a single status-board entry to `docs/agent/PROGRESS.md` (e.g., a one-line table row), but only if the engine has not already done so.
```

(The implementer should decide whether the DESIGN agent is the right place to maintain the PROGRESS.md status board, or whether a small post-DESIGN engine function should do it. Recommendation: **engine-side**, not agent-side. Add a `_update_progress_board(issue_num, stage)` helper in `core/engine.py` and call it at every stage transition. See Section 4.5.)

### 4.5 New helper: regenerate `PROGRESS.md` as a status board

Add a small helper to `core/engine.py` (place near other stage helpers, ~line 1090):

```python
def _update_progress_board(issue_num: int, stage: str, status: str) -> None:
    """Append/update a single status-board entry in PROGRESS.md.

    PROGRESS.md is a small human-readable queue, NOT a design log.
    The DESIGN agent no longer writes here (it writes to docs/designs/<N>.md).
    The engine maintains this file.

    Format (Markdown table):

        | #   | Title | Stage | Status |
        | --- | ----- | ----- | ------ |
        | 72  | [RISK-4] PositionSizer / MonteCarloEngine | build | 🔨 |
    """
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing entries (preserved across runs).
    existing: list[tuple[str, str, str, str]] = []  # (num, title, stage, status)
    if PROGRESS_FILE.exists():
        # ... parse existing table, drop rows whose num == issue_num ...
        pass

    # Fetch the issue title from gh (or pass it in from the caller).
    # For now, use a placeholder; the caller is expected to pass title.
    # (The implementer can refactor to take (issue_num, title, stage, status).)
    title = _fetch_issue_title(issue_num) or f"#{issue_num}"
    existing = [(n, t, s, st) for (n, t, s, st) in existing if n != str(issue_num)]
    existing.append((str(issue_num), title, stage, status))

    lines = [
        "# Ralph Queue",
        "",
        "Auto-generated status board. Per-issue design specs live in `docs/designs/<N>.md`.",
        "Detailed stage history lives in the GitHub issue comments.",
        "",
        "| # | Title | Stage | Status |",
        "| --- | ----- | ----- | ------ |",
    ]
    for n, t, s, st in sorted(existing, key=lambda r: int(r[0])):
        lines.append(f"| {n} | {t} | {s} | {st} |")
    lines.append("")

    PROGRESS_FILE.write_text("\n".join(lines), encoding="utf-8")
```

**Call sites:** add a call to `_update_progress_board(...)` after each stage transition:
- After DESIGN starts: `_update_progress_board(issue_num, "design", "🎨")`
- After DESIGN completes: `_update_progress_board(issue_num, "build", "🔨")`
- After BUILD completes: `_update_progress_board(issue_num, "verify", "🔍")`
- After VERIFY passes: `_update_progress_board(issue_num, "review", "✅")`
- On any stage failure: `_update_progress_board(issue_num, "blocked", "🛑")`

(Exact call sites are inside `run_pipeline()` and the stage runner functions. The implementer should grep for `transition_label(` to find good insertion points — these are the existing label-transition points where the status board entry should also be updated.)

`_fetch_issue_title(issue_num)` is a small wrapper around `gh issue view <num> --json title -q .title`. If the gh call fails (offline, rate-limit), return `None` and let the placeholder stand.

---

## 5. Migration / Backward Compatibility

| Existing state | Behavior after fix |
|---|---|
| Project has `PROGRESS.md` with appended designs | Stays as historical artifact. New design passes for new issues write to `docs/designs/<N>.md`. Old content in PROGRESS.md is never deleted by the engine. |
| Project has no `PROGRESS.md` | Engine creates a small status board on first run. |
| Project has both PROGRESS.md content and a per-issue `docs/designs/<N>.md` for the current issue | Per-issue file takes precedence. PROGRESS.md content is ignored for the current issue. |
| Test sub-agent prompt (Mode A) | Injects the per-issue file. If the per-issue file is missing, falls back to PROGRESS.md with a "may contain designs for other issues" warning. |
| Implement sub-agent prompt (Mode B) | Same injection logic as Mode A. In-session context from `--continue` still works. |

**No automatic migration of existing content.** Operators who want to move old designs from PROGRESS.md to per-issue files can do so manually, but it's not required for correctness — the legacy fallback handles it.

---

## 6. Affected Files

| File | Action | Notes |
|---|---|---|
| `core/engine.py` | UPDATE | Add `DESIGN_SPEC_DIR` + `_design_spec_path()` (Section 4.2); update `_summarize_design_spec()` (Section 4.3.A); update `_read_partial_design_spec()` (Section 4.3.B); update `_assemble_subagent_prompt()` Mode A/B block (Section 4.3.C); add `_update_progress_board()` + helper `_fetch_issue_title()` (Section 4.5); add call sites at every stage transition; update call sites of `_summarize_design_spec` and `_read_partial_design_spec` to pass `issue_num`. |
| `docs/agent/prompts/design.md` | UPDATE | Replace the "Your Goal" line (Section 4.4). Add constraint about not appending to PROGRESS.md. |
| `docs/designs/` | CREATE | New directory. Empty initially; populated by the DESIGN stage on first run of each new issue. |
| `docs/agent/PROGRESS.md` | TRIM (one-time, manual) | After the engine change is deployed, a one-time manual cleanup to a small status-board format. The engine then maintains it. (For new projects, this is automatic.) |

**No changes** to: `docs/agent/PROMPT.md`, `docs/agent/prompts/test.md`, `docs/agent/prompts/implement.md`, `docs/agent/prompts/verify.md`, `core/init.py`, `core/setup.py`, `core/status.py`, `core/validate.py`.

---

## 7. Acceptance Criteria

A reviewer (or the test sub-agent in the next design pass) should be able to verify each of the following independently:

### 7.1 Engine behavior

- [ ] `_design_spec_path(72)` returns `Path("docs/designs/72.md")` (relative to `PROJECT_ROOT`).
- [ ] When `docs/designs/72.md` exists, `_summarize_design_spec(72)` reads from it (not from `PROGRESS.md`), and the H1 of the summary matches the H1 of `docs/designs/72.md`.
- [ ] When `docs/designs/72.md` does NOT exist but `PROGRESS.md` does, `_summarize_design_spec(72)` falls back to `PROGRESS.md` and the function still returns a summary.
- [ ] When neither file exists, `_summarize_design_spec(72)` returns `None`.
- [ ] `_assemble_subagent_prompt(issue, "test.md", "A")` contains the contents of `docs/designs/<N>.md` (when it exists) in the `## Design Spec (from DESIGN stage)` section, and the section is labeled with the source path.
- [ ] `_assemble_subagent_prompt(issue, "implement.md", "B")` also contains the per-issue design spec, even though Mode B inherits session context (for robustness).
- [ ] After every stage transition, `PROGRESS.md` is regenerated by `_update_progress_board()` to a Markdown table with a row for the current issue. The current row's "Stage" column matches the current stage.

### 7.2 Prompt behavior

- [ ] The DESIGN prompt at `docs/agent/prompts/design.md` instructs the agent to write to `docs/designs/<issue-number>.md` (not `PROGRESS.md`).
- [ ] The DESIGN prompt explicitly says "Replace the file if it already exists. Do not append."
- [ ] The DESIGN prompt's "Constraints" section mentions that PROGRESS.md is a status board, not a design log.

### 7.3 End-to-end behavior

- [ ] Running the daemon against a new issue (e.g., create a test issue with label `status:ready`) results in the DESIGN agent writing to `docs/designs/<N>.md`, not to `PROGRESS.md`.
- [ ] The TEST sub-agent for that issue receives only that one design (verified by inspecting the captured prompt in the daemon log).
- [ ] The design summary posted as a GitHub issue comment for that issue has the correct H1 (matches `docs/designs/<N>.md`'s H1), not a stale H1 from a previous issue.
- [ ] `PROGRESS.md` after the run is a small Markdown table (< 200 lines) with one row per in-flight or recently-completed issue.
- [ ] The gap_scanner #72 incident pattern is impossible to reproduce: a TEST sub-agent can no longer receive specs for unrelated issues because there is no longer a shared file containing them.

### 7.4 Backward compatibility

- [ ] A project that has only `PROGRESS.md` (no `docs/designs/`) and no per-issue file still works: the fallback path in `_summarize_design_spec`, `_read_partial_design_spec`, and `_assemble_subagent_prompt` reads PROGRESS.md and the pipeline runs.
- [ ] Existing in-flight gap_scanner issues (e.g., #72) are not broken by this change. After redeploy, running `ralph daemon --issue=72` continues to make progress; the TEST sub-agent receives the same PROGRESS.md content (legacy fallback) and can complete.

---

## 8. Test Plan

1. **Unit-style smoke test in ralph infra repo:**
   - Add a small script (e.g., `scripts/test_design_path_resolution.py`) that:
     - Creates a temp directory with `docs/designs/72.md` containing a known H1.
     - Calls `_design_spec_path(72)` and asserts the path is correct.
     - Calls `_summarize_design_spec(72)` and asserts the H1 in the output matches.
   - Run with `ralph validate --tier=targeted` to ensure the script is picked up (or run it manually).

2. **End-to-end on a fresh test issue:**
   - In a test repo (or on the ralph infra repo itself), create a new issue with `status:ready` label.
   - Run `ralph daemon --issue=<N>`.
   - Inspect the resulting commit: confirm `docs/designs/<N>.md` was created with the design, and `docs/agent/PROGRESS.md` is a small table.
   - Capture the daemon log for the TEST sub-agent invocation and grep for "Design Spec" — confirm the source path in the injected prompt is `docs/designs/<N>.md` (not `PROGRESS.md`).

3. **Regression test on gap_scanner #72:**
   - After deploying the fix, run `ralph daemon --issue=72` against gap_scanner.
   - Verify the TEST sub-agent now receives a focused prompt (only #72's design, not the 15,865-line blob).
   - Verify the issue can be retried (the `status:build-retry` label is already set; the daemon should now make progress).

4. **Backward-compat test:**
   - In a scratch directory, manually create only `docs/agent/PROGRESS.md` (no `docs/designs/`).
   - Run `ralph validate` (or a no-op daemon invocation).
   - Verify no crash; verify the legacy fallback path is exercised (add a `print` or log line in the fallback branch during testing).

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `_update_progress_board()` clobbers a hand-edited `PROGRESS.md` | Medium | The function rewrites the file as a Markdown table. If an operator has hand-edits, they will be lost. Document this in the docstring and CHANGELOG. Recommend: treat PROGRESS.md as engine-managed; operators who want to add notes should add a comment-style section after the table, which the engine preserves (extend the parser to skip non-table lines). |
| Per-issue design file paths conflict with operator-added files | Low | Filename `<N>.md` is canonical. If an operator already has `docs/designs/72.md` with different content, the DESIGN agent will overwrite it. Document this; the agent's task is to write the design, not preserve prior content. |
| `_fetch_issue_title()` adds a `gh` call per stage transition → rate-limit | Low | `gh issue view` is cheap and cached by gh CLI. If it becomes a problem, batch the calls or accept a "title unknown" fallback. |
| Existing gap_scanner in-flight issues don't have per-issue design files | Medium (expected) | Legacy fallback to PROGRESS.md handles this. After the operator manually moves the #72 design to `docs/designs/72.md`, the issue can be re-run with full benefit. |
| Mode B sub-agent prompt grows by the size of the design file | Low | The design file is the same content the agent would receive via in-session context. Injecting it explicitly is a small token cost for a robustness win. |
| `_update_progress_board()` race condition if two daemons run | Low | Existing PID file (`acquire_pid_file()`) prevents two daemons. The status board is not concurrent-safe by design, but the daemon is single-instance. |

---

## 10. Open Questions

1. **Should `_update_progress_board()` be called by the engine, or by a separate post-stage hook?** Recommendation: engine-side, inline at every `transition_label()` call site. Simpler. No new architecture needed.
2. **Should `docs/designs/` be created by `ralph init` for new projects?** Recommendation: yes, add it to `core/init.py` next to the other directory-creation steps. Cheap and makes the convention visible to operators from day one.
3. **Should the DESIGN prompt's "Output Format" example reference `docs/designs/<N>.md` or stay generic?** Recommendation: update the example to reference the new path so the agent has a concrete template.
4. **Should we rename `PROGRESS.md` to something more accurate (e.g., `QUEUE.md` or `STATUS.md`)?** Recommendation: keep the name for backward compat, but update the H1 and content to be a status board. Operators familiar with the name won't be surprised. A follow-up rename can happen later if desired.
5. **Should the per-issue design file include a trailing "Stage History" section auto-populated by the engine?** Out of scope for this fix. The issue comments are the timeline; the design file is the spec. Keep them separate.

---

## 11. Process Notes for the Implementation Agent

You are the next pi / llm session picking up this design. Here's how to approach the work:

1. **Read this doc end-to-end first.** Don't skim. The acceptance criteria in Section 7 are your contract.
2. **Read the affected code in `core/engine.py`** at the exact line numbers in Section 4.3 (1298, 1368, 1558) and Section 4.5 (~line 1090). The line numbers are current as of this writing but may have drifted — search by function name if the line number is off.
3. **Read `docs/agent/prompts/design.md`** end-to-end before changing it. The "Output Format" section must be preserved; you're only changing the "Your Goal" line and adding a constraint.
4. **Make the engine changes in this order:**
   1. Add `DESIGN_SPEC_DIR` constant + `_design_spec_path()` helper.
   2. Update `_summarize_design_spec()` and its call site.
   3. Update `_read_partial_design_spec()` and its call site.
   4. Update `_assemble_subagent_prompt()` Mode A/B block.
   5. Add `_update_progress_board()` + `_fetch_issue_title()` helpers.
   6. Add `_update_progress_board()` call sites at every stage transition.
5. **Update `prompts/design.md`** last — only after the engine changes are in place, so you can verify the agent's output matches the new expectations.
6. **Run the existing test suite** (`ralph validate --tier=targeted`) after each change to catch regressions early.
7. **Do a manual end-to-end test** (Section 8 step 2) before declaring done. The unit tests aren't enough — this is a behavior change that needs a real daemon run to verify.
8. **Do not** change `docs/agent/PROMPT.md`, the `test.md` / `implement.md` / `verify.md` prompts, or the Mode B `--continue` session mechanism. They're out of scope.
9. **Commit message convention:** `[ralph] fix: isolate per-issue design specs from PROGRESS.md` (matching the existing `[ralph] fix: ...` style in `git log`).
10. **If you find a bug or gap in this spec**, fix it and update this doc in the same commit. Don't leave the doc out of sync with the code.

### Reference: existing related commits in `git log`

For style and convention:

```
29b62b5 fix(engine): protect all run_pipeline/stage calls from provider errors
ac63550 [ralph] fix: capture BUILD/VERIFY failures, archive evidence, rollback on failure, strengthen prompts
54b98af [ralph] fix: validate tracked test files exist on disk before passing to pytest
531bd7f [ralph] fix: detect when IMPLEMENT sub-agent modifies QA-written test files
```

These all touch `core/engine.py` with surgical, well-scoped changes. Follow the same pattern.

---

## 12. Changelog

- **2026-06-21** — Initial draft. Authored in response to gap_scanner #72 incident (TEST sub-agent received 15,865-line PROGRESS.md blob, exited non-zero, blocked the build). Previous fix `29b62b5` addressed a different bug (ProviderError unhandled in `run_pipeline`); this spec addresses the spec-isolation root cause.

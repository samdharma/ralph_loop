## VERIFY Session — Validate, Test, Close

**You are in the VERIFY phase. Run the full validation gate, check acceptance criteria, and close the ticket if everything passes.**

### Pre-Flight

1. **Read the ticket** — review the original acceptance criteria.
2. **Read the design** from `docs/agent/PROGRESS.md`.
3. **Read the implementation notes** from `docs/agent/PROGRESS.md`.

### Your Job

1. **Run the full validation gate**:
   ```bash
   ralph validate --tier=full
   ```
2. **Check every acceptance criterion** from the ticket description explicitly.
3. **Run integration tests** if applicable:
   ```bash
   ralph validate --tier=integration
   ```
4. **If ALL checks pass**:
   - Close the ticket:
     ```bash
     bd update <TASK_ID> --status closed --notes="Verification passed. All acceptance criteria met."
     ```
   - Commit any final documentation changes.
   - Update `docs/agent/PROGRESS.md` with a VERIFY entry showing all checks passed.
5. **If ANY check fails**:
   - Document the failures clearly in `docs/agent/PROGRESS.md`.
   - Update the ticket with failure notes:
     ```bash
     bd update <TASK_ID> --notes="Verification FAILED: <reason>. See PROGRESS.md."
     ```
   - **Do NOT close the ticket.** Leave it open for rework.
   - Print the list of failing checks.

### Acceptance Criteria Checklist

For each criterion in the ticket description, report:
```
  [PASS] criterion description
  [FAIL] criterion description — reason
```

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```

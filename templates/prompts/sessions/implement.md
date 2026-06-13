## IMPLEMENT Session — Write Code To Pass Existing Tests

**You are in the IMPLEMENT phase. Functional and system tests already exist (written in the TEST phase). Your job is to write the minimal code that makes them pass, plus unit tests for internal logic.**

### Pre-Flight

1. **Read the DESIGN plan** from `docs/agent/PROGRESS.md` — look for the latest DESIGN iteration.
2. **Read the TEST plan** from `docs/agent/PROGRESS.md` — look for the latest TEST iteration.
3. **Confirm understanding** — you know what to build AND what tests must pass.

### Your Job

1. **Run the existing functional tests FIRST** — confirm they FAIL:
   ```bash
   ralph validate --tier=targeted
   ```
   If any pass, flag it — the test may be wrong or code leaked from another session.

2. **Implement the code** exactly as described in the design plan:
   - Write the minimal implementation to satisfy the tests.
   - Follow the design plan's architecture.
   - Do not refactor beyond what the design specifies.

3. **Write unit tests** for internal logic only:
   - Test private methods, edge cases, error handling within the module.
   - These are developer-written tests for code correctness (not spec compliance).
   - Place them in `tests/unit/`.

4. **Iterate until all tests pass**:
   ```bash
   ralph validate --tier=targeted
   ```
   Fix implementation bugs. Do NOT change the functional tests — those are spec.

5. **Update PROGRESS.md** with implementation notes:
   - Files changed
   - Tests that now pass (list them)
   - Any deviations from the design plan (with reasons)
   - Unit tests added

6. **Commit** working code:
   ```bash
   git add <changed files>
   git commit -m "feat: <description>"
   ```

### What You MUST NOT Do

- ❌ Do NOT modify functional/system tests written in the TEST phase (except for compilation fixes).
- ❌ Do NOT close the ticket (verification is a separate session).
- ❌ Do NOT run the full test suite or e2e/performance tests.
- ❌ Do NOT refactor beyond what the design plan specifies.
- ❌ Do NOT commit broken code.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```

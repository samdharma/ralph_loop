## IMPLEMENT Session — Write Code, Test Locally

**You are in the IMPLEMENT phase. Write the implementation code.**

### Pre-Flight

1. **Read the design plan** from `docs/agent/PROGRESS.md` — look for the latest DESIGN iteration.
2. **Confirm understanding** — the design plan tells you what files to change and what tests to write.

### Your Job

1. **Implement** the code changes exactly as described in the design plan.
2. **Write tests** as specified in the design plan.
3. **Run targeted tests** (the tier specified in the task context). Default to `targeted`:
   ```bash
   ralph validate --tier=targeted
   ```
4. **Fix failures** — iterate until the targeted tests pass.
5. **Update PROGRESS.md** with implementation notes:
   - Files changed
   - Test results
   - Any deviations from the design plan
6. **Commit** working code:
   ```bash
   git add <changed files>
   git commit -m "feat: <description>"
   ```

### What You MUST NOT Do

- ❌ Do NOT close the ticket (verification is a separate session).
- ❌ Do NOT run full test suite or e2e/performance tests.
- ❌ Do NOT refactor beyond what the design plan specifies.
- ❌ Do NOT commit broken code.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```

## TEST Session — Write Functional & System Tests From Design

**You are in the TEST phase. Write tests from the design specification — NOT from implementation code (there is none). Here you focus on RED. GREEN and REFACTOR happen in the IMPLEMENT phase.**

---

### Workflow

1. **Read the DESIGN plan** from `docs/agent/PROGRESS.md` — find the latest DESIGN iteration.
2. **Read the ticket** — understand the acceptance criteria.
3. **Write tests that SHOULD FAIL** — there is no implementation yet. These tests prove the feature is needed.
4. **Map every acceptance criterion** to at least one test.
5. **Document the test plan** in `docs/agent/PROGRESS.md`:
   - Test file locations
   - What each test verifies
   - Which acceptance criterion each test covers
   - Expected failure modes

### Test Writing Rules

- **Test the spec, not the code.** Derive tests from acceptance criteria and the design plan.
- **Use descriptive names** that document expected behavior.
   - Good: `test_rejects_empty_password`
   - Bad: `test_password_validation`
- **Arrange-Act-Assert.** Each test sets up, performs one action, and asserts the outcome.
- **One concept per test.** Don't bundle multiple behaviors into one test.
- **DAMP over DRY.** Tests should read like specifications. Some duplication is fine if it makes each test self-contained.
- **Prefer real implementations** over mocks. Mock only at slow, non-deterministic, or external boundaries.
- **Cover the pyramid** — mostly small/fast unit tests, fewer integration tests, very few E2E tests.

### Test Coverage Map

For each acceptance criterion, map it to at least one test:
```
  Criterion: "User can reset password via email"
  → tests/integration/test_password_reset.py::test_reset_email_sent
  → tests/integration/test_password_reset.py::test_reset_token_valid
  → tests/unit/test_password_reset.py::test_token_expiry
```

### Anti-Rationalization

| Excuse | Reality |
|--------|---------|
| "I'll write tests after the code works." | Tests written after the fact test implementation, not behavior. |
| "This is too simple to test." | Simple code changes over time. Tests document expected behavior. |
| "I'll just mock everything." | Over-mocked tests pass while production breaks. |

### What You MUST NOT Do

- ❌ Do NOT write implementation code. NONE. There is no implementation yet.
- ❌ Do NOT write unit tests for internal logic (that's the IMPLEMENT session's job).
- ❌ Do NOT mock or stub the feature — test real behavior.
- ❌ Do NOT run the validation gate (tests will fail — that's expected).
- ❌ Do NOT close the ticket.

### Completion Signal

When finished, print exactly:
```
RALPH_SESSION_COMPLETE
```

"""GitHub client wrappers.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §7.2 and §10.2 B2.

Engine side effects (comments, label transitions, file writes) flow
through these wrappers to guarantee idempotency across crash/restart
cycles. Each call records its ``(run_id, action, target, body_hash)``
tuple to ``.ralph/issues/<N>/idempotency.jsonl`` BEFORE invoking ``gh``;
subsequent calls with the same tuple short-circuit.
"""

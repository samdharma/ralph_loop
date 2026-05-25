## Ops-Specific Guidance

- **Safety first**: Operations changes (deploy, restart, migration) must be idempotent and reversible.
- **Dry-run when possible**: Test ops scripts in a staging environment before production.
- **Rollback plan**: Every ops change must have a documented rollback procedure.
- **Monitor**: Add health checks and alerts for new operational changes.
- **Logs**: Ensure all ops actions are logged with timestamps.

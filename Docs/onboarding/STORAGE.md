# Local storage

The standard choice is SQLite with local artifacts. `[store].backend` must be set explicitly:

```toml
[store]
backend = "sqlite"
sqlite_path = "outputs/jobsearch.sqlite3"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"
```

SQLite tracks schema version 1. Replaying the same `run.run_key` replaces that run's stored opportunity rows rather than duplicating them. Canonical JSON payloads under `outputs/automation-payloads/` are the audit, replay and recovery boundary for this store; keep them.

Use `sync-pending-runs --target-store postgres` only after configuring and migrating optional PostgreSQL.

When several environments share one search, use the shared PostgreSQL store instead; each
environment then selects its connector with `JOBTRACKER_STORE_CONNECTOR`. See
[Shared PostgreSQL store](../DB/SHARED_STORE.md).

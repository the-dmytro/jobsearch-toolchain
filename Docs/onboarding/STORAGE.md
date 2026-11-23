# Local storage

SQLite and local artifacts are the default:

```toml
[store]
backend = "sqlite"
sqlite_path = "outputs/jobsearch.sqlite3"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"
```

SQLite tracks schema version 1. Replaying the same `run.run_key` replaces that run's stored opportunity rows rather than duplicating them. Canonical JSON payloads under `outputs/automation-payloads/` remain the audit, replay, and recovery boundary.

Use `sync-pending-runs --target-store postgres` only after configuring and migrating optional PostgreSQL.

When several environments share one search, use PostgreSQL with `required_backend`
so no write silently lands in a local file. See [Shared PostgreSQL store](../DB/SHARED_STORE.md).

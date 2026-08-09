# Writing a store connector

Built-ins are `sqlite` (default), `postgres`, and `memory`. A plugin uses `jobtracker.stores` and a factory accepting `ConnectorBuildContext`.

Every store implements exactly:

```python
upsert_run_payload(provider_slug: str, payload_path: str, report_path: str | None = None) -> UpsertResult
check_duplicates(provider_slug: str, company: str | None, title: str | None, external_id: str | None = None) -> list[DuplicateMatch]
export_application_summary(application_id: str) -> str
```

Writes must be idempotent by `run.run_key`. Canonical JSON payload files remain the replay boundary.

```toml
[project.entry-points."jobtracker.stores"]
private_store = "private_store.plugin:build_store"
```

```python
def build_store(context):
    return PrivateStore(root=context.root, options=dict(context.options))
```

Install from a local path or Git URL and set `[store].backend = "private_store"` in ignored config. Contract tests must cover upsert/replay, both duplicate lookup forms, export, unavailable dependencies, and secret-safe errors.

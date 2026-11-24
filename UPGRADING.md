# Upgrading

## v0.1.x to v0.2.0

1. Back up ignored `profile/`, `config/jobsearch.toml`, `.env`, and `outputs/` outside the public checkout.
2. Install or check out signed tag `v0.2.0` from GitHub.
3. Add `schema_version = 1` to config and profile TOML. Versionless files remain readable with a warning during v0.2.
4. Replace undocumented sections with `[paths]`, `[store]`, `[sources]`, `[mail]`, `[notify]`, and `[pipelines]`.
5. Set `[store].backend` explicitly (`sqlite` or `postgres`); there is no default. SQLite uses `outputs/jobsearch.sqlite3` unless `sqlite_path` says otherwise.
6. Update producers to emit `run`, `source_items`, and `opportunities`. Legacy `emails` and `jobs` remain read-compatible with warnings during v0.2.
7. Update plugins to a factory accepting `ConnectorBuildContext`. Zero-argument classes and instances are temporarily adapted with a deprecation warning.
8. Run offline doctor, fixture benchmark, the full test suite, and privacy scan.
9. Re-run a fixture pipeline twice and verify stable `run_key` idempotency.
10. If upgrading to PostgreSQL, migrate it and replay retained payloads with `sync-pending-runs --target-store postgres`.

## Shared store and database connectors (unreleased)

1. Remove `store.transport`, `store.connector` and `store.required_backend` from config files; they are rejected now.
2. For the PostgreSQL store, set `JOBTRACKER_STORE_CONNECTOR` in every environment (`postgres_direct` or `supabase_https`), and optionally declare `[store] hosting`.
3. Run `jobtracker migrate` to apply `007_portability_documents.sql` and `008_https_sql_gateway.sql`.
4. Optional: `jobtracker compact-db` (report), then `--apply --backup-confirmed` to drop legacy full-payload copies.
5. Make sure `profile/provider_targets.toml` exists; bundled fixture targets are no longer used in its place.

Do not copy private files into the public repository or force-add ignored paths. See the [public/private workflow](Docs/contributing/PUBLIC_UPSTREAM.md).

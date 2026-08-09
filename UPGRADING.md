# Upgrading

## v0.1.x to v0.2.0

1. Back up ignored `profile/`, `config/jobsearch.toml`, `.env`, and `outputs/` outside the public checkout.
2. Install or check out signed tag `v0.2.0` from GitHub.
3. Add `schema_version = 1` to config and profile TOML. Versionless files remain readable with a warning during v0.2.
4. Replace undocumented sections with `[paths]`, `[store]`, `[sources]`, `[mail]`, `[notify]`, and `[pipelines]`.
5. Select SQLite/local or PostgreSQL explicitly. SQLite defaults to `outputs/jobsearch.sqlite3`.
6. Update producers to emit `run`, `source_items`, and `opportunities`. Legacy `emails` and `jobs` remain read-compatible with warnings during v0.2.
7. Update plugins to a factory accepting `ConnectorBuildContext`. Zero-argument classes and instances are temporarily adapted with a deprecation warning.
8. Run offline doctor, fixture benchmark, the full test suite, and privacy scan.
9. Re-run a fixture pipeline twice and verify stable `run_key` idempotency.
10. If upgrading to PostgreSQL, migrate it and replay retained payloads with `sync-pending-runs --target-store postgres`.

Do not copy private files into the public repository or force-add ignored paths. See the [public/private workflow](Docs/contributing/PUBLIC_UPSTREAM.md).

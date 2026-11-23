# Changelog

All notable changes use semantic versions. The project is distributed from signed GitHub tags; PyPI publication is not part of v0.2.0.

## [Unreleased]

### Added

- Migration `007_portability_documents.sql`: `documents`, `opportunity_texts`, compact opportunity-card columns.
- `documents put/list/get`, `record-application`, `prune-local`, and `compact-db` commands.
- PostgreSQL automation state (`--state-backend`), so processed messages and sent reports are shared across environments.
- Store receipts with readback on `run` and `upsert-run`.
- Database connectors (DB-CONNECTOR-V1, entry point `jobtracker.db_connectors`): `postgres_direct` for any PostgreSQL host and `supabase_https` (migration `008`) for Supabase over HTTPS in HTTP-only sandboxes. Blueprint for new connectors.
- Per-environment config: `config/environments/<name>.toml` selected by `JOBTRACKER_ENVIRONMENT`; `[store] hosting` declares the provider when known.
- `probe-environment`: reports platform, repository state and each connector's status without changing anything.
- Environment setup guide with an agent procedure, `config/jobsearch.shared.example.toml`, `init --template shared --environment … --connector …`, `scripts/cloud/setup.sh` and `scripts/cloud/verify.sh`.

### Changed

- **Breaking:** `[store].backend` is required (no implicit SQLite default); PostgreSQL also requires a `connector` (normally per environment). All commands, including migrations, imports, `db-smoke`, `dedupe-candidates --include-db` and the `fetch-*` aliases, use only the configured store. There are no fallbacks to another store.
- Mail state (`fetch-mail-folder`, `send-report-email`) lives in the configured store and requires the config file.
- A missing `profile/provider_targets.toml` is an error instead of silently using bundled fixture targets.
- With PostgreSQL, duplicates are decided by the database only; local payload history is used only with SQLite.
- PostgreSQL report artifacts follow `store.artifact_backend`; a failed upload is an error.
- PostgreSQL rows no longer copy the full payload into `metadata`; full job texts follow `store.text_retention`.
- Replaying a payload with an application updates the existing application instead of inserting a duplicate.
- `sync-pending-runs` replays one file per `run_key` and does not overwrite a stored run that has more evaluations.
- After a verified PostgreSQL `run`, intermediate payloads are pruned (`store.auto_prune`).

## [0.2.0] - Unreleased

### Added

- Frozen v1 schemas for config, profile, automation payload, and doctor reports.
- Connector build context and factory entry points for sources, mail, stores, and notifiers.
- Local-first SQLite store, schema tracking, idempotent run replay, and PostgreSQL payload sync.
- Provider-neutral `fetch-source`, agent-led onboarding, manual setup book, plugin fixtures, and public-safety checks.

### Changed

- Canonical development moves to the public `jobsearch-toolchain` repository.
- SQLite/local artifacts are the default; PostgreSQL, Supabase, mail, notifications, scheduling, and CRM are optional.
- All configured relative paths resolve from the selected project root.
- The optional CRM now uses Next.js 16.3.0, keeps its scaffold CLI development-only,
  and ships with an npm lockfile that audits with zero known vulnerabilities.

### Removed

- Personalized public templates, default targeting, embedded cadence, temporary environment exceptions, and unsupported connector examples.

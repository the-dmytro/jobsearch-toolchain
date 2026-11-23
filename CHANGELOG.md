# Changelog

All notable changes use semantic versions. The project is distributed from signed GitHub tags; PyPI publication is not part of v0.2.0.

## [0.2.0] - Unreleased

### Added

- Frozen v1 schemas for config, profile, automation payload, and doctor reports.
- Connector build context and factory entry points for sources, mail, stores, notifiers, calendars and database connectors.
- Local-first SQLite store, schema tracking, idempotent run replay, and PostgreSQL payload sync.
- Provider-neutral `fetch-source`, agent-led onboarding, manual setup book, plugin fixtures, and public-safety checks.
- Optional calendar connector: `jobtracker calendar` subcommands, iCalendar/iTIP parsing, CalDAV and offline `icsdir` backends, the `jobtracker.calendars` entry-point group, and the `[calendar]` config table (backward-compatible CFG-V1 and CONNECTOR-V1 amendments).
- Database connectors (DB-CONNECTOR-V1, `jobtracker.db_connectors`): `postgres_direct` for any PostgreSQL host and `supabase_https` (migration `008`) for Supabase over HTTPS in HTTP-only sandboxes, plus a blueprint for new connectors.
- Environment-agnostic configuration: the repository config declares the database (`backend`, optional `hosting`); each environment selects its connector with its own variable `JOBTRACKER_STORE_CONNECTOR`.
- `probe-environment`: runtime capabilities, repository state and each connector's status, without identifying the platform or changing anything.
- Environment setup guide with an agent procedure, `config/setup-notes.example.md`, `config/jobsearch.shared.example.toml`, `init --template sqlite|shared [--hosting …]`, `scripts/environment/setup.sh` and `scripts/environment/verify.sh`.
- Migration `007_portability_documents.sql` (`documents`, `opportunity_texts`, compact opportunity-card columns); `documents put/list/get`, `record-application`, `prune-local` and `compact-db` commands.
- Shared PostgreSQL automation state (processed messages, sent reports, run events) and store receipts with readback on `run` and `upsert-run`.

### Changed

- Canonical development moves to the public `jobsearch-toolchain` repository.
- SQLite with local artifacts is the standard setup; PostgreSQL, Supabase, mail, notifications, scheduling, and CRM are optional.
- All configured relative paths resolve from the selected project root.
- The optional CRM now uses Next.js 16.3.0, keeps its scaffold CLI development-only,
  and ships with an npm lockfile that audits with zero known vulnerabilities.
- **Breaking:** `[store].backend` is required (no implicit default); the PostgreSQL store also requires `JOBTRACKER_STORE_CONNECTOR` in each environment. Every command uses only the configured store and connector, with no fallback to another store, connector or location.
- Mail state (`fetch-mail-folder`, `send-report-email`) lives in the configured store and requires the config file.
- A missing `profile/provider_targets.toml` is an error instead of silently using bundled fixture targets; source collection reads `[sources]` through the one config loader and never substitutes the example config.
- With PostgreSQL, duplicates are decided by the database only; local payload history is used only with SQLite.
- PostgreSQL report artifacts follow `store.artifact_backend`; a failed upload is an error.
- PostgreSQL rows no longer copy the full payload into `metadata`; full job texts follow `store.text_retention`.
- Replaying a payload with an application updates the existing application instead of inserting a duplicate.
- `sync-pending-runs` replays one file per `run_key` and does not overwrite a stored run that has more evaluations.
- After a verified PostgreSQL `run`, intermediate payloads are pruned (`store.auto_prune`).
- Persisting a collected run requires the configured store; `collect_provider_run` takes `store` only.

### Removed

- Personalized public templates, default targeting, embedded cadence, temporary environment exceptions, and unsupported connector examples.
- The `jobtracker.payloads` wrappers (use `PostgresJobStore`) and the unused `JOBTRACKER_STORE_BACKEND` setting.

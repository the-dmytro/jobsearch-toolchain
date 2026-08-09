# Changelog

All notable changes use semantic versions. The project is distributed from signed GitHub tags; PyPI publication is not part of v0.2.0.

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

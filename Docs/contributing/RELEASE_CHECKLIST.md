# v0.2 release checklist

## Contracts and tree

- [ ] Version, changelog, upgrade guide, schemas, examples, and connector fixtures agree.
- [ ] No conflict markers, unsupported APIs, personal facts, secrets, filled profiles, generated config, output, reports, or local databases are tracked.
- [ ] `python3 scripts/scan_pii.py` passes on the candidate tree and staged changes.
- [ ] Every reachable public branch/tag is enumerated and scanned before publication.

## Python

- [ ] Ruff check and format check pass.
- [ ] Full unittest suite passes with ResourceWarning treated as errors.
- [ ] Coverage is at least 85 percent across deterministic `jobtracker` modules except `__main__.py`.
- [ ] Contract, plugin fixture, docs-integrity, and fresh-clone acceptance tests pass.
- [ ] CI passes on macOS/Linux for Python 3.10 and current 3.14.
- [ ] PostgreSQL 16 integration replay passes on Linux.

## Optional CRM

- [ ] Node.js 20: `npm ci`, Vitest, ESLint, and production build pass.

## Fresh clone

- [ ] Create venv and install from the clone.
- [ ] Run fixture benchmark.
- [ ] Run `init`, fill a neutral temporary private profile, and pass offline doctor.
- [ ] Persist the fixture pipeline twice to SQLite and verify idempotency.
- [ ] Replay the same payload to PostgreSQL in CI.
- [ ] Confirm private/generated paths remain ignored and absent from clone history.

## Publication and rollback

- [ ] Preserve the pre-rewrite history only in the private repository.
- [ ] Obtain explicit approval for orphan rewrite, force-update, legacy branch deletion, signed tag, ruleset, and private overlay reconstruction.
- [ ] Verify signed `v0.2.0`, protected `main`, required green CI, disabled force pushes, and disabled branch deletion.
- [ ] Document that rewriting reduces reachability but cannot clear third-party caches; use hosting support if required.
- [ ] Keep retained JSON payload artifacts as the store-switch recovery boundary.

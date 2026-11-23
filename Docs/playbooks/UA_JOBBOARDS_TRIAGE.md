# Agent playbook: configured job-board triage

This compatibility-named playbook runs the providers selected in `config/jobsearch.toml`; it does not assume a country, role, seniority, salary, identity, or schedule.

## Inputs

- Selected project root and pipeline name.
- The pipeline profile and every private file it declares.
- Provider targets in the configured profile.
- User-approved notification and storage choices.

If any profile fact or connector choice is missing, ask. Never infer personal facts from job listings, old reports, templates, or examples.

## Deterministic sequence

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker run <pipeline-name> --dry-run
.venv/bin/python -m jobtracker run <pipeline-name>
```

For one configured provider:

```bash
.venv/bin/python -m jobtracker fetch-source <source-slug> --dry-run
```

The non-dry run writes canonical payload artifacts and persists through the configured `JobStore` and reads the run back. When a project moves from SQLite to PostgreSQL, replay retained payloads with `sync-pending-runs --target-store postgres`.

Use the model only for comparison, explanation, ranking, report prose, and explicitly requested drafting. Cite private profile evidence for judgments. Missing evidence becomes `Manual review needed`, not an invented claim.

Report exact providers attempted, payload paths, persistence and idempotency results, notifications sent, and blockers. A failed optional notification must not erase a valid local payload.

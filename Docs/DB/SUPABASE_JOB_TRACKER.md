# Optional PostgreSQL and hosted Supabase setup

The standard JobSearch Toolchain setup uses SQLite and local artifacts. Use this guide only when the user chooses shared PostgreSQL analytics or the optional CRM. Supabase is one supported hosted PostgreSQL provider; it is not required by the Python core.

Install the selected optional Python dependencies:

```bash
.venv/bin/pip install -e '.[postgres]'
# Add the hosted Storage client only when artifact uploads are selected.
.venv/bin/pip install -e '.[supabase]'
```

## Hosted Supabase

1. Create a hosted Supabase project.
2. Copy `.env.example` to ignored `.env`.
3. Set `JOBTRACKER_DATABASE_URL` to the hosted PostgreSQL connection string.
4. If Supabase Storage is selected, set the documented Supabase URL, server secret, and bucket variables.
5. Set `[store].backend = "postgres"` and `transport = "direct"` (or `"supabase_https"`, see [cloud environments](../onboarding/CLOUD_ENVIRONMENT.md)) in `config/jobsearch.toml`.
6. Apply migrations and check the connection:

```bash
.venv/bin/python -m jobtracker migrate
.venv/bin/python -m jobtracker db-smoke
```

Use the provider's TLS connection requirements. Keep connection strings and keys only in `.env`. The CLI is the supported database boundary; temporary environment-specific MCP exceptions do not belong in reusable playbooks.

## Replay local payloads

JSON payload artifacts are the recovery boundary when switching stores:

```bash
.venv/bin/python -m jobtracker sync-pending-runs \
  --payload-dir outputs/automation-payloads \
  --target-store postgres
```

Repeated `run_key` writes are idempotent. Keep the payload artifacts until replay and verification complete.

## PostgreSQL integration tests

CI runs PostgreSQL 16 as a service. A local PostgreSQL or Supabase stack is an advanced optional path and may use Docker, but Docker is not part of standard installation or acceptance.

```bash
SUPABASE_TEST_DB_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres \
  .venv/bin/python -m unittest tests.test_db_integration
```

The test URL must be local and must never equal the production URL.

## Optional CRM

The CRM requires Node.js 20 and hosted Supabase Auth plus the PostgreSQL analytics views. It is not needed for collection, SQLite tracking, payload replay, reports, or connector development. See [the CRM guide](../../crm/README.md).

## Data boundaries

For work across several machines or agents, follow [Shared PostgreSQL store](SHARED_STORE.md):
required backend, shared automation state, documents, and verified local cleanup.

- Structured shared data: selected PostgreSQL instance.
- Local recovery and audit boundary: ignored JSON payload artifacts.
- Long artifacts: local by default; optional object storage only when configured.
- Private profile, configuration, reports, and credentials remain ignored.

# Configuration

`config/jobsearch.example.toml` is the public v1 example. `jobtracker init` copies it to ignored `config/jobsearch.toml` and copies the neutral profile scaffold to ignored `profile/`. An optional ignored `config/jobsearch.local.toml` overlays the main file.

Relative paths are always resolved from `--root` or the selected project root, never from the shell's current directory.

## Supported sections

- `schema_version = 1`
- `[paths]`
- `[store]`
- `[sources.<slug>]`
- `[mail]`
- `[notify.<slug>]`
- `[pipelines.<name>]`

Machine-readable rules are in [`schemas/jobsearch-config.v1.schema.json`](../schemas/jobsearch-config.v1.schema.json). Configs without `schema_version` remain readable with a deprecation warning through v0.2.

## Store

`[store].backend` is required: `"sqlite"` or `"postgres"`. There is no default and no
fallback. PostgreSQL also needs `transport = "direct"` or `"supabase_https"`; see
[Shared PostgreSQL store](DB/SHARED_STORE.md) and [cloud environments](onboarding/CLOUD_ENVIRONMENT.md).

### Local-first store

```toml
[store]
backend = "sqlite"
sqlite_path = "outputs/jobsearch.sqlite3"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"
```

PostgreSQL is opt-in. `transport = "direct"` reads `JOBTRACKER_DATABASE_URL`; `transport = "supabase_https"` reads `SUPABASE_URL` and `SUPABASE_SECRET_KEY` from ignored `.env` or the environment.

## Pipeline

```toml
[pipelines.jobboards]
type = "jobboard"
profile = "generic"
providers = ["example_jsonld"]
include_db = true
max_pages = 1
```

Profile facts and provider targets live in ignored `profile/` files created from `profile/templates/generic/`.

## Config-only source

```toml
[sources.example_jsonld]
kind = "jsonld"
listing_url = "https://careers.example.invalid/jobs"
detail_limit = 10
```

Fetch it with `jobtracker fetch-source example_jsonld`. See [connector guides](connectors/README.md) for in-tree and plugin alternatives.

## Secrets

TOML stores non-secret choices only. Database URLs, mail passwords, API tokens, notification tokens, and storage keys belong in ignored `.env` using variables documented in `.env.example`.

## Validation

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker doctor
```

Offline doctor validates only configured local components and profile readiness. The full check adds network checks only for configured connectors.

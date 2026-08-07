# Configuration

## Layered config

| File | Purpose |
|------|---------|
| `config/jobsearch.toml` | Main config: identity, connectors, mail, store, pipelines |
| `config/jobsearch.local.toml` | Optional overrides (gitignored) |
| `profile/*.toml` | Search profiles (role lanes, source targets) |
| `.env` | Secrets: database URL, API keys, mail passwords |

## jobsearch.toml structure

```toml
[identity]
owner_name = "Your Name"
report_email = "jobs@example.com"

[store]
backend = "postgres"          # postgres | sqlite | memory
artifact_backend = "local"    # local | s3 | supabase-storage

[mail.inbox]
kind = "imap"
host = "imap.example.com"
user = "you@example.com"
# password via JOBTRACKER_IMAP_PASSWORD in .env

[mail.outbox]
kind = "smtp"
host = "smtp.example.com"
port = 465

[[pipelines]]
name = "jobboards"
profile = "ios"
sources = ["dou", "workua", "djinni"]
notify = ["email"]

[sources.example_board]
kind = "jsonld"
listing_url = "https://example.com/careers"
detail_limit = 10
```

## Search profiles

`profile/ios.toml` (created from `config/search-profile.example.toml`):

```toml
[role_lane]
name = "iOS/macOS"
include_terms = ["ios", "swift", "swiftui"]
exclude_terms = ["android", "flutter", "qa"]

[providers.dou]
feed_url = "https://jobs.dou.ua/vacancies/feeds/?category=iOS%2FmacOS"
default_detail_limit = 10
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JOBTRACKER_DATABASE_URL` | For DB writes | Postgres connection string |
| `SUPABASE_DB_URL` | Fallback | Deprecated; use above |
| `JOBTRACKER_IMAP_PASSWORD` | For mail fetch | IMAP app password |
| `JOBTRACKER_SMTP_*` | For reports | SMTP credentials |
| `JOBTRACKER_REPORT_EMAIL_TO` | For reports | Default report recipient |
| `CRM_OWNER_EMAIL` | For CRM | Comma-separated allowlist |

## Connector selection

Enable sources in `config/jobsearch.toml` or pass `--targets profile/ios.toml` to CLI commands.

Service-specific connectors (`dou`, `greenhouse`, `upwork`, etc.) ship enabled by default. Generic connectors need a `kind` field.

## Doctor checks

```bash
python -m jobtracker doctor           # full check
python -m jobtracker doctor --skip-network   # offline validation only
```

Validates: TOML schema, unfilled `{{PLACEHOLDER}}` tokens, connector `health()`, database reachability.

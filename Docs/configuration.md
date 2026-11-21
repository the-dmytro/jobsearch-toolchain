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
- `[calendar]`
- `[pipelines.<name>]`

Machine-readable rules are in [`schemas/jobsearch-config.v1.schema.json`](../schemas/jobsearch-config.v1.schema.json). Configs without `schema_version` remain readable with a deprecation warning through v0.2.

## Local-first store

```toml
[store]
backend = "sqlite"
sqlite_path = "outputs/jobsearch.sqlite3"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"
```

PostgreSQL is opt-in and reads its connection string from `JOBTRACKER_DATABASE_URL` in ignored `.env`.

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

## Calendar

```toml
[calendar]
kind = "caldav"
url = "https://caldav.example.com/"
calendar = "Interviews"
default_timezone = "UTC"
alarms_minutes = [60, 15]
cancel_prefix = "Cancelled: "
user_env = "JOBTRACKER_CALDAV_USER"
password_env = "JOBTRACKER_CALDAV_PASSWORD"
self_emails_env = "JOBTRACKER_CALENDAR_SELF_EMAILS"
```

| Key | Default | Meaning |
| --- | --- | --- |
| `kind` | `caldav` | `caldav`, `icsdir`, or a `jobtracker.calendars` plugin slug |
| `url` | none | CalDAV discovery root (required for `caldav` unless `calendar_url` is set) |
| `calendar_url` | none | Direct calendar collection URL; skips discovery |
| `path` | `outputs/calendar` | Root-relative folder for `icsdir` |
| `calendar` | `Interviews` | Calendar name; `--calendar` overrides it |
| `default_timezone` | `UTC` | Display zone, and the zone assumed for floating or unknown times |
| `alarms_minutes` | `[60, 15]` | Reminders before start; cancelled events have none |
| `cancel_prefix` | `Cancelled: ` | Title prefix for cancelled events |
| `user_env`, `password_env` | `JOBTRACKER_CALDAV_USER`, `JOBTRACKER_CALDAV_PASSWORD` | Environment variables that hold the credentials |
| `self_emails_env` | `JOBTRACKER_CALENDAR_SELF_EMAILS` | Environment variable that lists your own addresses |
| `timeout_seconds` | `60` | HTTP timeout for CalDAV |
| `[calendar.text_rules]` | none | Extra regular expressions per text-only action, for other languages |

Literal `user`, `password`, or `token` keys are rejected. See [Calendar](onboarding/CALENDAR.md).

## Secrets

TOML stores non-secret choices only. Database URLs, mail passwords, API tokens, notification tokens, and storage keys belong in ignored `.env` using variables documented in `.env.example`.

## Validation

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker doctor
```

Offline doctor validates only configured local components and profile readiness. The full check adds network checks only for configured connectors.

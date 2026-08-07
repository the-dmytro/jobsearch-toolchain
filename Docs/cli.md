# CLI command map

Commands from `jobtracker/cli.py` (`python -m jobtracker <command>`). Grouped by workflow; aliases are noted.

---

## Setup

| Command | Purpose |
|---------|---------|
| `init` | Scaffold `config/jobsearch.toml` and `profile/` from examples/templates |
| `doctor` | Validate config, profile placeholders; optional network checks for connectors/DB/IMAP/SMTP/notifiers |
| `migrate` | Apply SQL migrations under `db/migrations/` |
| `db-smoke` | Read-only DB connectivity smoke test (`--test` / `--write-test`) |

```bash
python -m jobtracker init
python -m jobtracker doctor --skip-network
python -m jobtracker migrate
```

---

## Discovery

| Command | Purpose |
|---------|---------|
| `fetch-dou` | Discover jobs from DOU and upsert (or `--dry-run`) |
| `fetch-workua` | Discover jobs from Work.ua |
| `fetch-djinni` | Discover jobs from Djinni |
| `fetch-greenhouse-jobs` | Discover jobs from Greenhouse boards (`--board-token`, `--max-boards`) |
| `benchmark-sources` | Fixture or `--live` benchmark across comma-separated providers |
| `prepare-jobboard-run` | Multi-provider fetch → validate → local/DB dedupe → manifest |

Shared fetch flags (where applicable): `--dry-run`, `--payload-out`, `--max-pages`, `--detail-limit`, `--targets`.

```bash
python -m jobtracker fetch-dou --dry-run --fixture-dir jobtracker/fixtures/provider_fetch
python -m jobtracker benchmark-sources --providers dou,workua,djinni,greenhouse
python -m jobtracker prepare-jobboard-run --profile ios --providers dou,workua,djinni
```

---

## Mail

| Command | Purpose |
|---------|---------|
| `discover-mail-folders` | List IMAP folders and resolve job-alert aliases |
| `discover-gmail-labels` | Alias for `discover-mail-folders` |
| `fetch-mail-folder` | Fetch provider messages from an IMAP folder into local source state |
| `fetch-gmail-label` | Alias for `fetch-mail-folder` |
| `parse-upwork-alerts` | Parse fetched Upwork alert emails into an automation payload |
| `send-report-email` | Send SMTP report with idempotency via local state DB |

```bash
python -m jobtracker discover-mail-folders
python -m jobtracker fetch-mail-folder --provider upwork --output outputs/mail/upwork.source.json
python -m jobtracker parse-upwork-alerts --source-payload outputs/mail/upwork.source.json
python -m jobtracker send-report-email --provider upwork --run-key RUN --subject "..." --body-file report.txt
```

---

## Persistence

| Command | Purpose |
|---------|---------|
| `upsert-run` | Upsert one automation run payload (`--provider`, `--payload`, optional `--report`) |
| `validate-payload` | Validate/normalize payload JSON to the contract |
| `check-duplicates` | Check whether company/title/external_id was already seen |
| `build-local-index` | Summarize local payload history for fallback dedupe |
| `dedupe-candidates` | Enrich a payload with local (and optional DB) duplicate evidence |
| `sync-pending-runs` | Upsert local payloads not yet marked DB-synced |
| `import-legacy` | Import legacy semicolon-delimited job-search CSV |
| `import-linkedin-tracking` | Import LinkedIn jobs / application tracker CSVs |
| `import-greenhouse` | Import Greenhouse application tracker CSV |

```bash
python -m jobtracker validate-payload --provider dou --payload path/to.payload.json
python -m jobtracker upsert-run --provider dou --payload path/to.deduped.payload.json
python -m jobtracker sync-pending-runs --payload-dir outputs/automation-payloads
```

---

## Reporting

| Command | Purpose |
|---------|---------|
| `export-summary` | Export a Markdown application summary (`--application-id`) |
| `send-report-email` | SMTP delivery of a prepared report body (also listed under Mail) |

---

## Automation

| Command | Purpose |
|---------|---------|
| `run` | Execute a named pipeline from `config/jobsearch.toml` (prepare → optional upsert → notify) |
| `prepare-jobboard-run` | Lower-level multi-board prepare used by `run` for `type = "jobboard"` |
| `doctor` | Preflight before scheduled runs |
| `sync-pending-runs` | Catch up offline/dry-run payloads |

```bash
python -m jobtracker run jobboards --dry-run
python -m jobtracker run jobboards
```

Pipeline definition example (`config/jobsearch.toml`):

```toml
[pipelines.jobboards]
type = "jobboard"
profile = "ios"
providers = ["dou", "workua", "djinni"]
include_db = true

[pipelines.jobboards.notify]
channels = ["email"]
```

See [architecture.md](architecture.md) for execution diagrams and [automation.md](automation.md) for playbooks and scheduling.

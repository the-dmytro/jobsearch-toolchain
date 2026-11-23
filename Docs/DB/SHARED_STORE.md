# Shared PostgreSQL store: continuity across environments

Use this when the same job search runs on more than one machine or agent (a laptop, a
server, an agent sandbox). PostgreSQL then holds everything that other
environments need: runs, opportunity cards, evaluations, applications, automation
state, and documents. Local files are temporary.

## One store, one connector per environment, no fallback

`[store].backend` is required and is the only database the project uses:

- `"sqlite"`: everything stays in the local SQLite file. Not shared.
- `"postgres"`: everything goes to one PostgreSQL database. Each environment reaches
  it through exactly one **connector**, named by that environment's variable
  `JOBTRACKER_STORE_CONNECTOR`. Built-in connectors: `postgres_direct` (any host,
  PostgreSQL protocol, `JOBTRACKER_DATABASE_URL`) and `supabase_https`
  (Supabase-hosted only, HTTPS, `SUPABASE_URL` + `SUPABASE_SECRET_KEY`). See
  [environment setup](../onboarding/ENVIRONMENT_SETUP.md) and the
  [connector blueprint](../connectors/writing-a-database-connector.md).

Connectors are alternatives: each reads only its own settings and none is tried when
another fails. If the configured store is unreachable, the command fails (exit code 2);
nothing is written anywhere else. Every write prints a receipt and is read back:

```json
{"persistence": "stored", "store": {"backend": "postgres", "connector": "supabase_https", "target": "ref.supabase.co", "shared": true, "hosting": "supabase", "selected_by": "JOBTRACKER_STORE_CONNECTOR"}, "verified": true}
```

```toml
# config/jobsearch.toml: the same in every environment
[store]
backend = "postgres"
hosting = "supabase"           # only if known
text_retention = "shortlisted" # shortlisted | all | none
auto_prune = true
prune_min_age_hours = 24
```

```text
# each environment's own variables (settings or ignored .env)
JOBTRACKER_STORE_CONNECTOR=postgres_direct     # e.g. where TCP to the database works
JOBTRACKER_STORE_CONNECTOR=supabase_https      # e.g. where only HTTPS leaves the sandbox
```

With `supabase_https` each statement commits on its own. Writes are idempotent and
read back, so if a command fails midway it exits non-zero and rerunning it completes
the write.

## Shared automation state

`fetch-mail-folder` and `send-report-email` keep their state in the configured store.
With PostgreSQL every environment sees which messages were already processed and which
reports were already sent (`source_items` processing columns, `email_notifications`,
`automation_run_events`). Both commands require `config/jobsearch.toml`.
Message bodies are not stored in this state; only a SHA-256 is kept.

## What PostgreSQL keeps

| Data | Stored as |
| --- | --- |
| Opportunity | Columns plus a compact card: `description_sha256`, `description_excerpt` (≤500 chars), `external_id_aliases`, `requirement_tags`, `metadata.facts` |
| Full job text | `opportunity_texts`, only when `text_retention` selects it (`shortlisted`: application, or an evaluation that recommends applying or shortlisting) |
| Source items | Columns, `body_sha256` and compact facts; `raw_text` only with `text_retention = "all"` |
| Run | Counters, status, `metadata.payload_sha256` of the payload file; no full payload copy |
| Report passed to `upsert-run --report` | `documents(kind = 'report')`; also uploaded when `artifact_backend` is `supabase`/`s3` (a failed upload is an error) |
| Drafts, cover letters, proposals, notes | `documents` via `documents put` |

Earlier versions stored a full payload copy in `metadata.payload` of every row.
`compact-db` removes those copies after you confirm a backup:

```bash
python -m jobtracker compact-db                       # report only
python -m jobtracker compact-db --apply --backup-confirmed --drop-unretained-texts
```

## Documents

```bash
python -m jobtracker documents put --kind cover_letter --status sent --file notes/cover.md \
  --organization "Example Co" --created-by human --delete-local
python -m jobtracker documents list --kind report
python -m jobtracker documents get --source-key notes/cover.md --output /tmp/cover.md
```

`--source-key` is the stable identity (default: the path relative to the root).
Writing the same key again updates the document. `--delete-local` removes the file
only after a read back that matches the stored content hash.

## Confirmed applications

```bash
python -m jobtracker record-application --file application.json --job-text-file posting.txt
```

```json
{
  "confirmed": true,
  "organization": "Example Co",
  "title": "Mobile Engineer",
  "provider": "linkedin",
  "external_id": "linkedin:1234567890",
  "external_id_aliases": ["ats:req-42"],
  "source_url": "https://jobs.example.invalid/42",
  "applied_at": "2026-11-08",
  "salary_requested_text": "EUR 70,000",
  "salary_requested_min": 70000,
  "salary_requested_currency": "EUR",
  "events": [{"event_type": "applied", "event_at": "2026-11-08", "title": "Applied"}]
}
```

The command reconciles by every known ID and alias. It never creates a second
application for the same opportunity and does not repeat existing events. Replays of
payloads with an `application` object also update instead of duplicating.
`--job-text-file` (or a `job_text` field) keeps the full posting in `opportunity_texts`.

## Local cleanup

```bash
python -m jobtracker prune-local                 # plan only
python -m jobtracker prune-local --apply
```

A file is deleted only when the database holds its content:

- a payload whose `run_key` is stored and whose content hash matches the stored run;
- a raw, normalized or deduped variant of a stored run, or a manifest whose runs are
  all stored;
- a report identical to a stored document.

Everything else is kept with a reason. Pruning is refused when the store is not
PostgreSQL. After a verified `run`, `auto_prune` deletes that run's raw and normalized
payloads immediately and prunes older verified rounds.

## Dedupe

With PostgreSQL, duplicates are decided by the database only, so every environment
gets the same answer. Local payload history is a dedupe source only for the SQLite
store.

## Replay of local artifacts

`sync-pending-runs` moves retained local payloads into the configured PostgreSQL store
(for example after switching from SQLite). It refuses to run unless the config names
PostgreSQL. It replays one file per `run_key`, the most final variant (evaluated, then
deduped, raw, normalized). It skips a file that
is identical to the stored run. It refuses to overwrite a stored run that has more
evaluations than the local file; `--overwrite-richer` overrides this.

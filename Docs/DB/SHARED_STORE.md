# Shared PostgreSQL store: continuity across environments

Use this when the same job search runs on more than one machine or agent (a laptop, a
cloud session, another coding agent). PostgreSQL then holds everything that other
environments need: runs, opportunity cards, evaluations, applications, automation
state, and documents. Local files are temporary.

## Explicit persistence

Every write reports where it went and whether it was read back:

```json
{"persistence": "stored", "store": {"backend": "postgres", "target": "db.host.example", "shared": true}, "verified": true}
```

There is no silent local fallback:

- Set `required_backend = "postgres"` in `[store]` (or `JOBTRACKER_REQUIRED_STORE=postgres`
  in the environment). Any command that would open another store backend fails.
- If PostgreSQL is unreachable, writes fail with exit code 2. Only an explicit
  `--journal-on-db-failure` flag (`run`, `upsert-run`) keeps the payload in the local
  journal, prints `"persistence": "pending_sync"` and exits with code 3.
- `doctor` lists journaled runs under `checks.pending_sync` and reports
  `action_required` until `sync-pending-runs` has replayed and verified them.

```toml
[store]
backend = "postgres"
required_backend = "postgres"
text_retention = "shortlisted"   # shortlisted | all | none
auto_prune = true
prune_min_age_hours = 24
```

## Shared automation state

`fetch-mail-folder` and `send-report-email` take `--state-backend auto|sqlite|postgres`.
`auto` follows `[store].backend`, so with PostgreSQL every environment sees which
messages were already processed and which reports were already sent
(`source_items` processing columns, `email_notifications`, `automation_run_events`).
Message bodies are not stored in this state; only a SHA-256 is kept.

## What PostgreSQL keeps

| Data | Stored as |
| --- | --- |
| Opportunity | Columns plus a compact card: `description_sha256`, `description_excerpt` (≤500 chars), `external_id_aliases`, `requirement_tags`, `metadata.facts` |
| Full job text | `opportunity_texts`, only when `text_retention` selects it (`shortlisted`: application, or an evaluation that recommends applying or shortlisting) |
| Source items | Columns, `body_sha256` and compact facts; `raw_text` only with `text_retention = "all"` |
| Run | Counters, status, `metadata.payload_sha256` of the payload file; no full payload copy |
| Report passed to `upsert-run --report` | `documents(kind = 'report')` plus the Storage artifact when configured |
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
python -m jobtracker record-application --file application.json
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

## Replay

`sync-pending-runs` replays one file per `run_key`: the journaled file, otherwise the
most final variant (evaluated, then deduped, raw, normalized). It skips a file that
is identical to the stored run. It refuses to overwrite a stored run that has more
evaluations than the local file; `--overwrite-richer` overrides this.

# CLI command map

Run commands as `python -m jobtracker <command>`. Add `--root /path/to/project` to the
root-aware setup, pipeline, source, mail, store, and replay commands when the shell is
not already at the project root.

## Standard local workflow

| Command | Purpose |
| --- | --- |
| `init` | Copy the neutral config and profile templates into ignored private paths |
| `doctor` | Validate the v1 config/profile and only the components the user configured |
| `run <pipeline>` | Collect, validate, deduplicate, retain artifacts, and optionally persist/notify |
| `fetch-source <slug>` | Run any configured, built-in, or plugin source |
| `upsert-run` | Persist one PAYLOAD-V1 artifact through the configured `JobStore` |
| `check-duplicates` | Query the configured `JobStore` through STORE-V1 |
| `export-summary` | Export one application summary through the configured `JobStore` |

```bash
python -m jobtracker init                    # or: init --template shared
python -m jobtracker doctor --skip-network
python -m jobtracker run jobboards --dry-run --fixture-dir jobtracker/fixtures/provider_fetch
python -m jobtracker run jobboards --fixture-dir jobtracker/fixtures/provider_fetch
```

The generated config uses SQLite at `outputs/jobsearch.sqlite3`. `--dry-run` writes
deterministic artifacts but does not persist or notify. All paths in the config and
root-aware commands resolve from the selected root, not the shell working directory.

## Sources

```bash
python -m jobtracker fetch-source example_jsonld --dry-run
python -m jobtracker benchmark-sources --providers dou,workua,djinni,greenhouse
```

The v0.2 compatibility aliases are `fetch-dou`, `fetch-workua`, `fetch-djinni`, and
`fetch-greenhouse-jobs`. They remain supported, but new workflows should use
`fetch-source <slug>` and `[sources.<slug>]`.

`prepare-jobboard-run` is a lower-level compatibility command. It requires explicit
`--profile` and `--providers`; normal automation should use a named pipeline.

## Mail

Mail is optional. The commands below consume `[mail.inbox]`, `[mail.parsers.<slug>]`,
and `[mail.outbox]` when present. Without those sections, the IMAP/SMTP environment
configuration remains compatible.

```bash
python -m jobtracker discover-mail-folders
python -m jobtracker fetch-mail-folder --provider example --output outputs/mail/example.source.json
python -m jobtracker send-report-email \
  --provider example \
  --run-key example-2026-01-01 \
  --subject "Job-search report" \
  --body-file outputs/report.txt
```

`discover-gmail-labels` and `fetch-gmail-label` are compatibility aliases.
`parse-upwork-alerts` remains available for the existing Upwork message format.

## Payloads, dedupe, and store switching

```bash
python -m jobtracker validate-payload --provider example --payload outputs/example.payload.json
python -m jobtracker upsert-run --provider example --payload outputs/example.payload.json
python -m jobtracker build-local-index --payload-dir outputs/automation-payloads
python -m jobtracker dedupe-candidates \
  --provider example \
  --payload outputs/example.payload.json \
  --output outputs/example.deduped.payload.json
```

After opting into PostgreSQL, replay retained recovery artifacts with:

```bash
python -m jobtracker sync-pending-runs \
  --target-store postgres \
  --payload-dir outputs/automation-payloads
```

The replay state database prevents already-synced `run_key` values from being sent
again. Repeated writes of a run to SQLite and PostgreSQL are idempotent.

## Shared store, documents, and cleanup

With PostgreSQL as the shared store, these commands keep work portable across
environments. They never write to a local fallback. See
[Shared PostgreSQL store](DB/SHARED_STORE.md).

| Command | Purpose |
| --- | --- |
| `documents put/list/get` | Store and read drafts, reports, cover letters, notes |
| `record-application` | Idempotently record a confirmed application from JSON |
| `prune-local` | Delete local artifacts whose content is verified in the database |
| `compact-db` | Remove legacy full-payload copies; apply job-text retention |

If the configured store is unreachable, these commands and `run`/`upsert-run` fail;
nothing is written elsewhere.

## Optional PostgreSQL and imports

`migrate` and `db-smoke` target configured PostgreSQL/Supabase credentials. CSV import
commands are `import-legacy`, `import-linkedin-tracking`, and `import-greenhouse`.
They are migration helpers, not part of the fresh local setup. PDF link recovery in
legacy imports requires the `legacy-import` optional dependency.

See [configuration](configuration.md), [architecture](architecture.md), and the
[onboarding book](README.md).

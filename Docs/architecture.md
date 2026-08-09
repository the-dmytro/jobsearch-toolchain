# Architecture

JobSearch is a local-first deterministic toolchain with optional service connectors,
notifications, PostgreSQL/Supabase persistence, and a Next.js CRM. The standard path
is Python plus SQLite and retained JSON artifacts; no Docker service is required.

## Runtime and boundaries

```mermaid
flowchart LR
  Private["Ignored private files<br/>profile/ + config/jobsearch.toml + .env"] --> Config["CFG-V1 loader<br/>root-relative paths"]
  Config --> Run["CLI pipeline"]
  Run --> Sources["Source factories<br/>config + in-tree + plugins"]
  Run --> Mail["Optional inbox/parser factories"]
  Sources --> Payload["PAYLOAD-V1 JSON artifacts"]
  Mail --> Payload
  Payload --> Dedupe["Deterministic validation + dedupe"]
  Dedupe --> Store["STORE-V1"]
  Store --> SQLite[("SQLite default")]
  Store -. opt-in .-> PG[("PostgreSQL / hosted Supabase")]
  Run -. opt-in .-> Notify["Notifier/sender factories"]
  PG -. optional .-> CRM["Next.js CRM + analytics views"]
```

The CRM does not import Python and Python does not import CRM code. Secrets are read
from environment variables; config contains only non-secret connector settings.

## Pipeline execution

```mermaid
flowchart TD
  Start["run <pipeline> --root ..."] --> Load["Load CFG-V1 + private profile"]
  Load --> Resolve["Resolve each source with ConnectorBuildContext"]
  Resolve --> Collect["Collect source_items + opportunities"]
  Collect --> Validate["Validate and normalize PAYLOAD-V1"]
  Validate --> Local["Local artifact history dedupe"]
  Local --> StoreDedupe["Configured JobStore duplicate check"]
  StoreDedupe --> Artifacts["Write payload, normalized, deduped, manifest"]
  Artifacts --> Persist{"dry run or include_db=false?"}
  Persist -->|yes| Done["Return evidence"]
  Persist -->|no| Upsert["Idempotent JobStore upsert by run_key"]
  Upsert --> OptionalNotify["Optional configured notifications"]
  OptionalNotify --> Done
```

SQLite and PostgreSQL implement the same `upsert_run_payload`, `check_duplicates`,
and `export_application_summary` operations. JSON payloads are the recovery boundary:
`sync-pending-runs --target-store postgres` replays retained artifacts after a user
opts into PostgreSQL.

## Connector resolution

Every plugin factory receives `ConnectorBuildContext(root, slug, options)`. Legacy
zero-argument classes or instances are adapted with a deprecation warning through
the v0.2 compatibility window.

| Product | Built-in/config route | Plugin entry-point group |
| --- | --- | --- |
| Source | `[sources.foo] kind = "jsonld"` or an in-tree service | `jobtracker.sources` |
| Mail parser | Built-in parser or `kind = "rules"` | `jobtracker.mail.parsers` |
| Mail inbox | IMAP or maildir | `jobtracker.mail.inboxes` |
| Mail sender | SMTP | `jobtracker.mail.senders` |
| Store | SQLite, PostgreSQL, memory | `jobtracker.stores` |
| Notifier | Email/webhook/Slack/Telegram | `jobtracker.notifiers` |

See the [connector contract](contracts/connector-api-v1.md) and the installable
[fixture plugin](../examples/plugins/fixture-connectors/README.md).

## Config and private data

```mermaid
flowchart TB
  Example["Tracked neutral examples"] --> Init["init"]
  Init --> Primary["config/jobsearch.toml<br/>ignored"]
  Init --> Profile["profile/*<br/>ignored"]
  Local["config/jobsearch.local.toml<br/>ignored"] --> Merge["validated deep merge"]
  Primary --> Merge
  Env[".env<br/>ignored secrets"] --> Components["configured connectors"]
  Merge --> App["AppConfig"]
  Profile --> App
  App --> Components
```

The machine-readable schemas under `schemas/` are authoritative. Configs without a
`schema_version` remain readable with a warning through v0.2; new configs use version
1. Doctor reports use DOCTOR-V1 and exit 0 for `ready`, 1 for `action_required`, and 2
for `error`.

See [configuration](configuration.md), [CLI reference](cli.md), and the
[documentation index](README.md).

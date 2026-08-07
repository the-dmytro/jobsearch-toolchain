# Architecture

Hub overview of the JobSearch toolchain: CLI orchestration, pluggable connectors, Postgres persistence, and the Next.js CRM. Diagrams below are verified against `jobtracker/automation.py`, `sources/registry.py`, `mail/registry.py`, `app_config/loader.py`, `notify/registry.py`, and `jobboard_run.py`.

Related docs: [getting-started](getting-started.md) · [configuration](configuration.md) · [cli](cli.md) · [automation](automation.md) · [DB ERD](DB/ERD.md) · [payload contract](DB/AUTOMATION_PAYLOAD_CONTRACT.md)

---

## a. System overview

CLI loads layered config, runs discovery or mail pipelines through connector registries, upserts into Postgres, notifies configured channels, and the CRM reads analytics views.

```mermaid
flowchart LR
  subgraph CLI["python -m jobtracker"]
    Init["init / doctor"]
    Run["run / prepare-jobboard-run"]
    Fetch["fetch-* / fetch-mail-folder"]
    Upsert["upsert-run / sync-pending-runs"]
  end

  subgraph Connectors["Connector layers"]
    Sources["sources/<br/>JobSource registry"]
    Mail["mail/<br/>inbox + AlertParser"]
    Store["store/<br/>PostgresJobStore"]
    Notify["notify/<br/>email webhook Slack Telegram"]
  end

  PG[(Postgres)]
  CRM["crm/ Next.js<br/>dashboard + insights"]
  Out["outputs/<br/>payloads · manifests · state"]

  Init --> Config["config/jobsearch.toml<br/>+ profile/ + .env"]
  Run --> Config
  Config --> Sources
  Config --> Mail
  Config --> Notify
  Fetch --> Sources
  Fetch --> Mail
  Sources --> Out
  Mail --> Out
  Run --> Store
  Upsert --> Store
  Store --> PG
  Run --> Notify
  Notify --> External["SMTP / webhooks / chat"]
  PG --> CRM
```

---

## b. Discovery data flow

`collect_provider_run` resolves a source, calls `discover`, builds a contract payload, optionally writes JSON, and upserts when not dry-run.

```mermaid
flowchart TD
  A["collect_provider_run(provider)"] --> B["Load targets + jobsearch sources"]
  B --> C["resolve_source<br/>kind → generic | registry | entry point"]
  C --> D["CollectionContext<br/>fetcher · options · metrics"]
  D --> E["source.discover(ctx)"]
  E --> F["_build_payload<br/>run · opportunities · source_items · metrics"]
  F --> G{"dry_run?"}
  G -->|yes + payload_out| H["Write payload JSON"]
  G -->|yes, no out| I["Return CollectionResult only"]
  G -->|no| J["_write_payload"]
  J --> K["upsert_run_payload → PostgresJobStore"]
  K --> L["automation_runs<br/>opportunities<br/>source_items<br/>evaluations"]
  H --> M["CollectionResult"]
  I --> M
  K --> M
```

---

## c. Connector registry and extension paths

Three ways to add a source (same pattern for mail parsers and notifiers via their entry-point groups).

```mermaid
flowchart TD
  Req["Provider slug requested"] --> Kind{"kind in<br/>[sources.slug] or targets?"}
  Kind -->|yes| Gen["build_generic_source<br/>rss · jsonld · html · json_api · sitemap · csv"]
  Kind -->|no| Reg{"source_registry.get(slug)"}
  Reg -->|hit| Svc["In-tree @register_source<br/>dou · workua · djinni · greenhouse · lever · ashby"]
  Reg -->|miss| EP["Entry points<br/>jobtracker.sources"]
  EP -->|loaded| Plugin["Out-of-tree plugin package"]
  EP -->|none| Err["UnknownConnectorError"]

  Gen --> Src[JobSource]
  Svc --> Src
  Plugin --> Src
```

| Path | Mechanism | Example |
|------|-----------|---------|
| Config only | `[sources.foo] kind = "jsonld"` | Generic boards with structured markup |
| In-tree service | Class under `sources/services/` + `@register_source` | DOU, Greenhouse |
| Plugin | `[project.entry-points."jobtracker.sources"]` | Private connector package |

Mail parsers use `jobtracker.mail.parsers`; notifiers use `jobtracker.notifiers`; stores follow the same registry idea under `jobtracker/store/`.

---

## d. Mail pipeline

IMAP (or maildir) fetch → provider filter → parser → automation payload.

```mermaid
flowchart LR
  Inbox["inbox_factory<br/>imap | maildir"] --> Fetch["fetch messages<br/>folder aliases from .env"]
  Fetch --> Filter{"message_matches_provider"}
  Filter -->|own report| Skip["Skip"]
  Filter -->|upwork / linkedin / parser.matches| Keep["Matched messages"]
  Keep --> State["AutomationStateStore<br/>source items"]
  Keep --> Parser["AlertParser<br/>upwork · linkedin · ats_ack"]
  Parser --> Payload["Automation payload JSON"]
  Payload --> Upsert["upsert-run → Postgres"]
```

CLI surface: `discover-mail-folders` → `fetch-mail-folder` → `parse-upwork-alerts` (and playbook-driven parsers for other providers) → `upsert-run` / `send-report-email`.

---

## e. Pipeline execution

`run_pipeline` loads config and profile, delegates prepare/dedupe to `prepare_jobboard_run`, then optionally upserts and notifies.

```mermaid
flowchart TD
  R["run_pipeline(name)"] --> L["load_app_config + load_profile"]
  L --> P["prepare_jobboard_run"]
  subgraph Prepare["prepare_jobboard_run"]
    P1["For each provider"]
    P1 --> P2["collect_provider_run dry_run=True"]
    P2 --> P3["Annotate + write .payload.json"]
    P3 --> P4["validate_payload → .normalized"]
    P4 --> P5["LocalDedupeIndex + dedupe_payload"]
    P5 --> P6["Optional DB duplicate enrichment"]
    P6 --> P7["Write .deduped.payload.json"]
    P7 --> P8["Write manifest JSON"]
  end
  P --> Store{"include_db and not dry_run?"}
  Store -->|yes| U["upsert_run_payload per provider"]
  Store -->|no| SkipStore["Skip DB"]
  U --> N{"notify_channels?"}
  SkipStore --> N
  N -->|yes, not dry_run| Notify["build_notifier → notify_all"]
  N -->|no / dry_run| Done["Return manifest · stored · notifications"]
  Notify --> Done
```

Manifest lists deterministic steps completed and LLM/agent steps remaining (evaluate, report, email) for playbook follow-up.

---

## f. Config layering

Secrets stay in `.env`; non-secret automation settings merge from TOML overlays and profile files.

```mermaid
flowchart TB
  Example["config/jobsearch.example.toml"] -.->|init copies| Primary["config/jobsearch.toml"]
  Primary --> Merge["_deep_merge"]
  Local["config/jobsearch.local.toml<br/>optional, gitignored"] --> Merge
  Merge --> AppConfig["AppConfig<br/>paths · pipelines · notify"]
  Profile["profile/&lt;slug&gt;.toml"] --> LoadProfile["load_profile"]
  Targets["profile/provider_targets.toml<br/>or fixtures"] --> Collect["collect_provider_run targets"]
  Env[".env<br/>JOBTRACKER_DATABASE_URL<br/>IMAP/SMTP · report email"] --> Settings["load_settings / connect / mail"]
  AppConfig --> Run["run_pipeline"]
  LoadProfile --> Run
  Collect --> Run
  Settings --> Run
```

| Layer | Tracked | Role |
|-------|---------|------|
| `config/jobsearch.toml` | Yes (user-created) | Pipelines, notify channels, paths |
| `config/jobsearch.local.toml` | No | Machine-specific overrides |
| `profile/*.toml` | No | Search profile, targets path, report templates |
| `.env` | No | DB URL, mail passwords, API keys |

See [configuration.md](configuration.md) for variable tables and TOML shape.

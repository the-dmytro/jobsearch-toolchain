# Agent guidelines

## Purpose

This repo is a job-search automation toolchain. Agents should help users configure connectors, run pipelines, and maintain profile data — without inventing personal facts or committing secrets.

## Invariants

1. **Profile truth** — facts about the user come only from `profile/` files they filled in, never invented
2. **Payload contract** — automation JSON must match `Docs/DB/AUTOMATION_PAYLOAD_CONTRACT.md`
3. **No secrets in git** — credentials live in `.env` only
4. **No personal data in public commits** — run `python3 scripts/scan_pii.py` before push
5. **Layer boundaries** — CRM (`crm/`) does not import Python; Python does not import CRM

## Where user data lives

| Path | Tracked | Contents |
|------|---------|----------|
| `profile/` | No (gitignored) | CV, preferences, project banks, provider targets |
| `config/jobsearch.toml` | Yes (user creates from example) | Connectors, pipelines, non-secret settings |
| `.env` | No | Database URLs, API keys, mail passwords |
| `outputs/` | No | Generated payloads, reports |
| `Docs/Tracking/` | No | Historical triage reports |

On the `personal` branch, `profile/` may be force-added for backup. Never push `personal` to the public `origin` remote.

## Connector extension

- **Config only**: `[sources.foo] kind = "jsonld"` in TOML
- **In-tree**: class in `jobtracker/sources/services/` with `@register_source`
- **Plugin**: `[project.entry-points."jobtracker.sources"]` in a separate package

Same pattern for `jobtracker.mail.parsers`, `jobtracker.stores`, `jobtracker.notifiers`.

## Key CLI commands

```bash
python -m jobtracker init
python -m jobtracker doctor [--skip-network]
python -m jobtracker run <pipeline> [--dry-run]
python -m jobtracker migrate
python -m jobtracker upsert-run --provider <slug> --payload <path>
```

## Playbooks

Agent workflows: `Docs/playbooks/`. Replace `{{OWNER_NAME}}`, `{{REPORT_EMAIL}}`, `{{WORKSPACE_ROOT}}` before execution.

## CRM

Next.js 16 App Router. Read `crm/node_modules/next/dist/docs/` before changing CRM code. Dashboard reads Postgres views (`v_funnel_summary`, etc.) — not full table scans.

## Testing

```bash
python -m unittest discover -s tests
python3 scripts/scan_pii.py
cd crm && npm run build
```

## Learned preferences

- Prefer Cursor-documented practices for `.cursor` setup
- `.cursor` tracking via global gitignore, not repo-local

# Environment setup

An *environment* is any place where the toolchain runs: a personal computer, a
server, a CI job, or a hosted agent sandbox. Environments differ in what they can
reach and which tools they offer, and new kinds keep appearing. The toolchain does
not know or detect which kind it runs in. The agent doing the setup finds out by
probing and asking, then records the choice in that environment's own settings.

An agent asked to "set up an environment for this toolchain" follows
[the agent procedure](#agent-procedure).

## What lives where

| What | Where | Environment-specific? |
| --- | --- | --- |
| Which database: `[store] backend`; where it is hosted, if known: `hosting` | `config/jobsearch.toml` (repository) | no |
| Verified findings from earlier setups | `config/setup-notes.md` (repository, private) | no — it is shared knowledge *about* environments |
| How this environment reaches the database | the variable `JOBTRACKER_STORE_CONNECTOR` | yes |
| The connector's settings and secrets (`JOBTRACKER_DATABASE_URL`, `SUPABASE_URL`, keys, …) | this environment's variables / secrets, or its ignored `.env` | yes |

The repository never lists environments. Each environment carries its own variables,
set in that environment's settings (or in its ignored `.env` on a machine you
control). Stores, automation state and documents talk to every connector through the
same connection interface ([DB-CONNECTOR-V1](../connectors/writing-a-database-connector.md)).

Rules that the code enforces:

- With `backend = "postgres"`, `JOBTRACKER_STORE_CONNECTOR` must name exactly one
  connector. There is no default and no guess; commands fail until it is set.
- `store.connector` in a config file is rejected. `config/jobsearch.local.toml` must
  not change `backend` or `hosting`.
- Connectors are alternatives. Each reads only its own settings, none is tried when
  another fails, and a provider-specific connector is refused when `hosting`
  declares another provider.
- A failed write is an error. Nothing is redirected to another store or location.

## Built-in connectors

| Connector | Reaches | Network needed | Settings |
| --- | --- | --- | --- |
| `postgres_direct` | any PostgreSQL host | TCP to the database port | `JOBTRACKER_DATABASE_URL` |
| `supabase_https` | Supabase-hosted PostgreSQL only | HTTPS to `<ref>.supabase.co` | `SUPABASE_URL`, `SUPABASE_SECRET_KEY`; migration `008` in the database |

`supabase_https` commits each statement on its own; writes are idempotent and read
back. `jobtracker probe-environment` lists every registered connector, including
plugins, with its live status. To reach another provider or another kind of
database, follow the [database connector blueprint](../connectors/writing-a-database-connector.md).

## Agent-side tools

Agents may have tools that the Python toolchain cannot call, for example an MCP
connector for the database provider. Use them, with the user's consent where they
change data, for inspection, readback checks, and bootstrap steps (such as applying
migration `008`) when no toolchain connector can reach the database yet. Toolchain
writes always go through the selected connector. If only an agent-side tool reaches
the database, report it and the options (another connector, or a new one from the
blueprint); never route toolchain data through the agent.

## Agent procedure

Do not guess what a probe or the user can answer. When you are not certain that an
option works in this environment, test it or ask before acting.

### 1. Discover

- Read `AGENTS.md`, this page, `Docs/DB/SHARED_STORE.md`, and `config/setup-notes.md`
  if it exists.
- Inspect the repository: `config/jobsearch.toml` (`backend`, `hosting`), the profile
  (`profile/provider_targets.toml`, profile Markdown files), configured sources and
  mail settings.
- Classify the setup:
  - **new project**: no config or no profile; the user creates the database and
    connections with you;
  - **existing project**: config and profile exist and the database already holds
    data from other environments. Keep that database; only choose how this
    environment reaches it.

### 2. Probe

```bash
.venv/bin/python -m jobtracker probe-environment --format text
```

It reports runtime facts (proxy variables, Python, drivers), the repository state,
and every connector's status (`available`, `reachable`, `blocked`, `not_configured`,
`not_applicable`) with evidence and missing settings. It changes nothing and prints
no secret values.

Then establish what the probe cannot see:

- your own tools (for example MCP connectors for the database provider, mail or
  calendar) and whether a harmless read works;
- the platform's controls: can you set variables, secrets, network rules or a setup
  script, or must the user do it?

### 3. Ask the user

In one batch, ask only what you could not establish:

- where the database is hosted, unless `hosting` or the setup notes say so. A
  PostgreSQL URL alone does not identify Supabase, Neon or any other provider;
- for a new project: local-only SQLite or a shared PostgreSQL database, and which
  provider;
- which credentials they can provide. Never ask for secret values in chat; use the
  platform's secure credential mechanism or tell them where to enter the value.

### 4. Decide realistic options

- Offer a connector only if its `hosting` is `any` or matches the declared hosting.
- A connector whose network is blocked here is not an option here, even if the
  setup notes say it works elsewhere.
- For an existing project, never propose another database; propose only ways to
  reach the existing one.
- If nothing fits, say so and offer: a network change if the platform allows one,
  another connector for the same provider, or a new connector from the blueprint.

Present the options with evidence and a recommendation; wait for the user's choice.

### 5. Configure

New project:

```bash
.venv/bin/python -m jobtracker init                                  # SQLite, one place only
.venv/bin/python -m jobtracker init --template shared [--hosting <provider>]
```

`init` skips files that exist, so an existing project's config is kept. In this
environment's settings (or its ignored `.env`):

- `JOBTRACKER_STORE_CONNECTOR=<chosen connector>`;
- the connector's non-secret settings;
- its secrets through the platform's secret mechanism. If the platform injects a
  secret into requests itself (for example as an HTTP header for one host), set the
  variable the connector requires to a placeholder such as `proxy-injected`;
- network rules for the hosts the connector and the configured sources need;
- [`scripts/environment/setup.sh`](../../scripts/environment/setup.sh) as the setup or
  provisioning script, if the platform has one.

A new shared database gets its schema through the chosen connector
(`jobtracker migrate`). For `supabase_https`, migration `008` must exist first:
apply it through another connector that works somewhere, have the user paste it into
the Supabase SQL editor, or apply it with an agent-side tool after the user agrees.

### 6. Verify

In a session running on this environment:

```bash
scripts/environment/verify.sh
```

It prints the probe summary and runs `jobtracker doctor` through the selected
connector.

### 7. Record and report

- Add what you verified to `config/setup-notes.md` (copy
  `config/setup-notes.example.md` if it is missing): the kind of environment, what
  the network and tools allowed, the connector chosen, the date. No secrets. Commit
  it in the private repository.
- Report every step as done, blocked (name the host, variable, secret or migration),
  or left to the user, with the exact place where they must act.

## Repository layouts

- **Private copy (recommended for continuity).** A private repository or branch
  tracks `profile/`, `config/jobsearch.toml` and `config/setup-notes.md` (the public
  `.gitignore` ignores them; a private overlay `.gitignore` tracks them).
- **Public toolchain only.** Profile and config are ignored and may be lost with the
  environment. Use it to try the toolchain.

## Supabase Free notes

The free plan pauses a project after a week without activity and has no automatic
backups. Make backups from the dashboard or with `pg_dump`, or use a paid plan.

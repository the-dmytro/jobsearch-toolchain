# Environment setup

Use this guide whenever the toolchain must run in a new place: a laptop, a cloud
agent session (Claude Code on the web, Codex cloud, …), CI, or a server. Environments
differ in what they can reach and which tools they have. An agent asked to "set up an
environment for this toolchain" follows [the agent procedure](#agent-procedure).

## Three layers

| Layer | Question | Where it is decided |
| --- | --- | --- |
| Database | *Which* data store holds the project? | `config/jobsearch.toml`: `[store] backend` (`sqlite` or `postgres`) and, if known, `hosting` (for example `supabase`) |
| Connector | *How* does this environment reach that database? | `config/environments/<environment>.toml`: `[store] connector` |
| Environment | *Which* of those files applies here? | the variable `JOBTRACKER_ENVIRONMENT=<environment>` set in that environment |

Stores, automation state and documents talk to every connector through the same
connection interface ([DB-CONNECTOR-V1](../connectors/writing-a-database-connector.md)),
so the rest of the toolchain does not change between environments.

Rules that the code enforces:

- One environment uses exactly one connector. Connectors are alternatives: none is
  tried when another fails, and none reads another's credentials.
- `JOBTRACKER_ENVIRONMENT` is never guessed. If the shared config needs a connector
  and the variable is unset or names a missing file, commands fail and list the
  available environments.
- `config/jobsearch.local.toml` must not change `backend`, `connector` or `hosting`.
- A failed write is an error. Nothing is redirected to another store or location.

## Built-in connectors

| Connector | Reaches | Network needed | Settings | Notes |
| --- | --- | --- | --- | --- |
| `postgres_direct` | any PostgreSQL host | TCP to the database port | `JOBTRACKER_DATABASE_URL` | transactional |
| `supabase_https` | Supabase-hosted PostgreSQL only | HTTPS to `<ref>.supabase.co` | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | each statement commits on its own; needs migration `008` |

`jobtracker probe-environment` lists every registered connector, including plugins,
with its live status in the current environment. To reach another provider or
another kind of database, follow the
[database connector blueprint](../connectors/writing-a-database-connector.md).

## Agent-side tools

Agents may also have tools that the Python toolchain cannot call, for example an MCP
connector for the database provider. Use them for what they are good at, with the
user's consent where they change data:

- inspecting the schema and data, confirming a readback, checking table sizes;
- applying a bootstrap migration (for example `008`) when no toolchain connector
  can reach the database yet.

Toolchain writes still go through the configured connector. If only an agent-side
tool can reach the database, report that and the options (a different connector or
a new one built from the blueprint); do not route toolchain data through the agent.

## Agent procedure

Work through these steps in order. Do not guess anything that a probe or the user
can answer. When you are not certain an option works in this environment, test it
or ask before acting.

### 1. Discover

- Read `AGENTS.md`, this page, and `Docs/DB/SHARED_STORE.md`.
- Inspect the repository: is there a `config/jobsearch.toml`? Which `backend` and
  `hosting` does it declare? Which files exist in `config/environments/`? Is the
  profile filled (`profile/provider_targets.toml`, profile Markdown files)?
- Classify the setup:
  - **new user**: no config or no profile. The user will create the database and
    connectors with you.
  - **existing project**: config and profile exist and the database already holds
    data, set up from another environment. Reuse its database; add a new
    environment file for this place.

### 2. Probe

```bash
.venv/bin/python -m jobtracker probe-environment --format text
```

It reports the platform, whether an HTTP(S) proxy is present, the repository state,
and every connector's status (`available`, `reachable`, `blocked`,
`not_configured`, `not_applicable`) with evidence and missing settings. It never
prints secret values and never changes anything.

Then add what the probe cannot see:

- your own tool list (for example MCP connectors for the database provider, mail or
  calendar) and whether a harmless read works;
- the platform's environment controls (network policy, variables, secrets, setup
  script) and what you are allowed to change.

### 3. Ask the user

Ask only for what you could not establish, in one batch:

- where the database is hosted, if `hosting` is not declared and nothing explicit
  says so. A PostgreSQL URL alone does not mean Supabase, Neon or any other provider;
- for a new user, whether they want local-only SQLite or a shared database, and
  which provider they plan to use;
- which credentials they can provide. Never ask for secret values in chat; use the
  platform's secure credential form or tell them where to enter the value.

### 4. Decide realistic options

Combine probe results, declared facts and the user's answers:

- Offer a connector only if its `hosting` is `any` or matches the declared hosting.
- A connector whose `network` is blocked here (for example `postgres_wire` behind an
  HTTP-only proxy) is not an option in this environment, even if it works elsewhere.
- If no connector fits, say so plainly and offer: a different network setting if the
  platform has one, another connector for the same provider, or a new connector from
  the blueprint.
- For an existing project, never propose a different database; propose only ways to
  reach the existing one.

Present the options with the evidence and your recommendation, then wait for the
user's choice.

### 5. Configure

For the chosen connector, with the user's approval:

```bash
# new user with a shared database
.venv/bin/python -m jobtracker init --template shared --environment <name> --connector <connector> [--hosting <provider>]
# existing project: add only the environment file
.venv/bin/python -m jobtracker init --template shared --environment <name> --connector <connector>
```

(`init` skips files that already exist, so the shared config of an existing project is
kept. Commit the new `config/environments/<name>.toml` in a private repository.)

In the platform's environment settings:

- set `JOBTRACKER_ENVIRONMENT=<name>`;
- add the connector's non-secret settings (for example `SUPABASE_URL`);
- request secrets through the secure form (for `supabase_https` on a proxy that
  injects headers: host `<ref>.supabase.co`, header `apikey`, then set
  `SUPABASE_SECRET_KEY=proxy-injected`);
- allow the hosts the connector and the configured sources need;
- use [`scripts/cloud/setup.sh`](../../scripts/cloud/setup.sh) as the setup script.

New database: create the schema through the chosen connector
(`jobtracker migrate`). For `supabase_https`, migration `008` must exist first: the
user pastes `db/migrations/008_https_sql_gateway.sql` into the Supabase SQL editor
once, or you apply it with an agent-side database tool after the user agrees.

### 6. Verify

In a session that runs on the configured environment:

```bash
scripts/cloud/verify.sh
```

It prints the probe summary and runs `jobtracker doctor`, which connects through
the selected connector.

### 7. Report

List every step as done, blocked (name the host, setting, secret or migration), or
left to the user, with the exact place where they must act.

## Platform notes

Verified facts only; re-probe when in doubt.

| Platform | Observed | Consequence |
| --- | --- | --- |
| Claude Code cloud sessions | Outbound traffic only through an HTTP(S) proxy; raw TCP to PostgreSQL (5432/6543) and IMAP (993) refused even with full network access (verified 2026-11-23). Environment variables, header-injected network secrets and setup scripts are available. MCP connectors attached to the account are usable by the agent. | `postgres_direct` blocked. `supabase_https` works for Supabase-hosted databases. Mail inboxes need an agent-side mail connector exported to maildir; reports go through HTTPS notifiers. |
| Codex cloud | Not verified here. | Probe before choosing a connector. |
| Your own computer | Usually unrestricted. | `postgres_direct` typically works with the provider's connection string. |

## Repository layouts

- **Private copy (recommended for continuity).** A private repository or branch
  tracks `profile/`, `config/jobsearch.toml` and `config/environments/*.toml` (the
  public `.gitignore` ignores them; a private overlay `.gitignore` tracks them).
  Every environment starts with the same profile, database declaration and
  environment files.
- **Public toolchain only.** Profile and config are ignored and disappear with the
  session. Use it only to try the toolchain.

## Supabase Free notes

The free plan pauses a project after a week without activity and has no automatic
backups. Make backups from the dashboard or with `pg_dump`, or use a paid plan.

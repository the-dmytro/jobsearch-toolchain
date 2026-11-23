# Cloud environments

Use this to run the toolchain in a cloud agent session (Claude Code on the web,
Codex cloud, or similar) and to continue the same search from any machine. An agent
asked to "set up a cloud environment for this toolchain" follows
[the agent procedure](#agent-procedure) at the end.

After setup, the person only enters secrets and variables in the environment settings.
Everything else comes from the repository.

## How it fits together

| Part | Where it lives |
| --- | --- |
| Code, schemas, playbooks | The repository (public toolchain or your private copy) |
| Profile facts, provider targets, `config/jobsearch.toml` | Your private repository or branch (see [layouts](#repository-layouts)) |
| Runs, opportunities, applications, automation state, documents | One shared Supabase PostgreSQL database |
| Secrets | The environment's secrets / network secrets, never the repository |
| Local outputs | Temporary; pruned after the database holds them |

The config names exactly one store. With `backend = "postgres"` every command reads
and writes that database and fails when it is unreachable. Nothing is redirected to a
local file. `backend = "sqlite"` keeps everything on one machine and is not shared.

## Network: HTTP-only sandboxes

Hosted agent sandboxes usually allow only HTTP(S) through a proxy. A raw PostgreSQL
(5432/6543), IMAP (993) or SMTP (465/587) connection is refused there, so:

- Use `transport = "supabase_https"`. It sends each statement to the Supabase Data
  API (`POST https://<project-ref>.supabase.co/rest/v1/rpc/jobtracker_sql`) and reaches
  the same database as `transport = "direct"`.
- Mail inboxes and SMTP are unavailable. For alert emails, export messages with the
  platform's mail connector into a maildir folder and configure
  `[mail.inbox] kind = "maildir"`, `path = "outputs/maildir"`. For reports, use an
  HTTPS notifier (`telegram`, `slack`, `webhook`).
- Every job-board host you fetch must be on the environment's allowed hosts list.

A project uses exactly one transport, the one in `config/jobsearch.toml`. The two are
alternatives, not complements: `direct` never uses Supabase API keys, `supabase_https`
never uses `JOBTRACKER_DATABASE_URL`, and neither is tried when the other fails. For
work across cloud sandboxes and your own machines, choose `supabase_https` everywhere.
Changing the transport is a deliberate config change, not something the toolchain does.

## One-time database preparation

1. Create a Supabase project (free tier is enough for a personal search).
2. Create the schema through the transport you chose:
   - **`supabase_https`:** the HTTPS gateway is itself created by migration `008`, so
     paste `db/migrations/008_https_sql_gateway.sql` once into the Supabase SQL editor.
     Then run `jobtracker migrate` (via `.venv/bin/python -m`); it applies the other migrations
     over HTTPS. Only `service_role` may execute the gateway function.
   - **`direct`:** run `jobtracker migrate` (via `.venv/bin/python -m`) with
     `JOBTRACKER_DATABASE_URL` set.
3. Supabase Free pauses a project after a week without activity and has no automatic
   backups. Make backups with the Supabase dashboard or `pg_dump`, or use a paid plan.

## Repository layouts

- **Private copy (recommended).** A private repository, or a private branch such as
  `personal`, contains the toolchain plus your tracked `profile/` and
  `config/jobsearch.toml`. Use the private-overlay `.gitignore`: track `profile/**`
  and the non-secret config, ignore binaries, `outputs/`, `.env*` and
  `config/jobsearch.local.toml`. Every environment then starts with the same profile
  and config.
- **Public toolchain only.** The checkout has no profile. Run
  `jobtracker init --template cloud` and complete onboarding. The profile files are
  ignored, so they are lost when the session ends. Use this only to try the toolchain.

Keep the store choice (`backend`, `transport`) in the tracked config only, so every
environment uses the same one. Do not override it in `config/jobsearch.local.toml`.

## Environment settings

Network access: limited, with package managers allowed, plus these hosts:

| Host | Needed for |
| --- | --- |
| `<project-ref>.supabase.co` | Database over HTTPS (Data API) and Storage |
| `jobs.dou.ua`, `www.work.ua`, `djinni.co` | Built-in Ukrainian job boards, if used |
| `boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com` | ATS sources, if used |
| hosts of every `[sources.*] listing_url` | Config-only sources |
| `api.telegram.org`, `hooks.slack.com`, your webhook host | HTTPS notifications, if used |

Variables (not secret):

```text
SUPABASE_URL=https://<project-ref>.supabase.co
```

Secrets:

| Name | How |
| --- | --- |
| Supabase secret key (`sb_secret_…`, or the legacy `service_role` key) | Preferred: a network secret for host `<project-ref>.supabase.co`, header `apikey`, no prefix; then also set the variable `SUPABASE_SECRET_KEY=proxy-injected`. Otherwise: variable `SUPABASE_SECRET_KEY` |
| `TELEGRAM_BOT_TOKEN`, Slack webhook URL | Variables referenced by `bot_token_env` / `webhook_url_env`, only if used |

The secret key bypasses row-level security. Do not use it in a browser, a public
repository, or an environment shared with people who must not read your data.

Setup script: the body of [`scripts/cloud/setup.sh`](../../scripts/cloud/setup.sh).
It creates `.venv` and installs the toolchain in every checkout it finds. It does not
read secrets.

## Each session

```bash
scripts/cloud/verify.sh
```

It checks that the variables for the configured store are present (values are never
printed) and that `profile/provider_targets.toml` exists. Then it runs `jobtracker doctor`,
which connects to the configured store. Fix every reported issue before working.

Then follow the normal playbooks. Store results only through the CLI
(`upsert-run`, `record-application`, `documents put`) and finish rounds with
`prune-local --apply`. See [Shared PostgreSQL store](../DB/SHARED_STORE.md).

## Codex and other platforms

The same files apply: setup script `scripts/cloud/setup.sh`, the variables above, and
the allowed hosts. If the platform cannot inject a header secret, set
`SUPABASE_SECRET_KEY` as a secret variable. Keep `transport = "supabase_https"` unless
you have verified a direct PostgreSQL connection works from that platform.

## Agent procedure

When asked to set up a cloud environment for this toolchain:

1. Read this page, `AGENTS.md`, and `Docs/DB/SHARED_STORE.md`. Identify the layout
   (private copy or public only) and the checkout's name.
2. Confirm `config/jobsearch.toml` names `backend = "postgres"` with
   `transport = "supabase_https"`. In a private copy, commit that change; never invent
   profile facts.
3. Ask the person for the Supabase project URL. Never ask for the secret key in chat.
4. Create or update the environment with the platform's environment tools: allowed
   hosts from the table above (only the sources the config uses), `SUPABASE_URL`, and
   the setup script from `scripts/cloud/setup.sh`. Request the Supabase secret key
   through the platform's secure credential form (host `<project-ref>.supabase.co`,
   header `apikey`), then set `SUPABASE_SECRET_KEY=proxy-injected`.
5. If the database is new, have the schema created once through the chosen transport
   (see [preparation](#one-time-database-preparation)).
6. In a new session on that environment, run `scripts/cloud/verify.sh`. Report each
   check as passed, or blocked with the named host, variable or migration.

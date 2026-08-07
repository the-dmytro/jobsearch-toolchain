# Getting started

## Prerequisites

- Python 3.10+
- PostgreSQL (local via [Supabase CLI](https://supabase.com/docs/guides/cli) or hosted Supabase)
- Optional: Node.js 20+ for the CRM

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## 2. Initialize configuration

```bash
python -m jobtracker init
```

This creates:

- `config/jobsearch.toml` from `config/jobsearch.example.toml`
- `profile/` files from `profile/templates/`

## 3. Fill your profile

Edit files under `profile/`:

| File | Purpose |
|------|---------|
| `00_INSTRUCTIONS.md` | Agent operating rules |
| `01_PREFERENCES.md` | Role, location, dealbreakers |
| `04_LINKS_AND_CONTACTS.md` | Email, LinkedIn, GitHub |
| `CV_SOURCE.md` | Primary CV markdown |
| `project-banks/*.md` | Per-project evidence |

Replace every `{{PLACEHOLDER}}` token.

## 4. Configure environment

```bash
cp .env.example .env
```

Minimum for database writes:

```
JOBTRACKER_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

For local Supabase:

```bash
supabase start
```

## 5. Migrate and verify

```bash
python -m jobtracker migrate
python -m jobtracker doctor
python -m jobtracker db-smoke
```

## 6. First dry-run

```bash
python -m jobtracker fetch-dou \
  --dry-run \
  --fixture-dir jobtracker/fixtures/provider_fetch \
  --payload-out outputs/provider_fetch/dou.payload.json
```

Inspect the payload JSON, then run without `--dry-run` to persist.

## 7. CRM (optional)

```bash
cd crm && npm install && npm run dev
```

Add to `.env`:

```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
CRM_OWNER_EMAIL=you@example.com
```

## Next steps

- [Configuration reference](configuration.md)
- [Automation](automation.md)
- [Writing a source connector](connectors/writing-a-source.md)

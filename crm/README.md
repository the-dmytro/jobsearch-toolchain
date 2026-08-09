# JobSearch CRM (Next.js)

DB-first UI for the `jobtracker` Supabase schema: dashboard, applications (list + kanban), company/contact/communication/interview views, transcripts, automation runs, insights.

## Prereqs

- Supabase project with migrations applied (including `003_crm_rls_policies.sql`).
- Auth: enable Email (magic link). Redirect URLs must include your app origin and `/auth/callback`.
- Table `crm_owner_allowlist` must include your login email (insert after migrate; see migration 003 comment).
- Storage bucket `job-artifacts` (private). RLS allows authenticated owner to read objects.

## Environment

Copy [`.env.example`](../.env.example) to `crm/.env.local` (or use root `.env` for monorepo).

| Variable | Client | Server | Notes |
|----------|--------|--------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | yes | yes | Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | yes | yes | Anon key (RLS) |
| `NEXT_PUBLIC_SITE_URL` | optional | optional | Override app origin; on Vercel auto-detects from `VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL` (localhost value is ignored on Vercel) |
| `CRM_OWNER_EMAIL` | — | yes | Comma-separated allowlist; must match Supabase Auth user email(s) |
| `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY` | — | yes (server only) | Signed URLs for artifacts via `getArtifactSignedUrl` |

## Dev

```bash
cd crm
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — you will be redirected to `/login` until signed in.

## Security (no Vercel Deployment Protection required)

The publishable Supabase key is public in the browser bundle by design. Protection is in Postgres:

- Migration `005_crm_allowlist_rls.sql` enables RLS on `crm_owner_allowlist` and revokes API access — the owner gate cannot be rewritten via REST.
- Domain tables stay behind `crm_is_owner()` policies for `authenticated` only.
- `CRM_OWNER_EMAIL` middleware is UI defense-in-depth only; RLS is the real control.
- Keep `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY` server-only (never `NEXT_PUBLIC_`).

To add another owner: insert into `crm_owner_allowlist` with service role or `jobtracker` direct DB access, and add the email to `CRM_OWNER_EMAIL`.

## Deploy (Vercel)

1. Create a Vercel project with root directory `crm` (or monorepo with that subfolder).
2. Set the env vars above in Vercel project settings.
3. Add the same environment variables in local `.env` for preview if needed.
4. In Supabase **Authentication → URL configuration**, add the Vercel production and preview URLs.

## Keyboard

- `⌘K` / `Ctrl+K` — command palette (navigation).

## Migrations

Apply from repo root (Python venv):

```bash
.venv/bin/python -m jobtracker migrate
```

This runs `db/migrations/*.sql` in order, including CRM RLS.

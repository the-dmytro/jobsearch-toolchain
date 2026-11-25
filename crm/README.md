# JobSearch CRM (Next.js)

DB-first UI for the `jobtracker` Supabase schema: dashboard, applications (list + kanban), company/contact/communication/interview views, transcripts, automation runs, insights.

Dashboard and insights figures are computed in the browser (`lib/analytics.ts`) from one cached raw read of the tables, loaded in keyset pages. The SQL `v_*` views are not used by the CRM.

## Prereqs

- Node `>=20.9`. CI tests Node 20 and 24, and Vercel builds on Node 24.
- Supabase project with migrations applied (including `003_crm_rls_policies.sql`).
- Auth: enable Email (magic link). Redirect URLs must include your app origin and `/auth/callback`.
- Table `crm_owner_allowlist` must include your login email (insert after migrate; see migration 003 comment).
- Storage bucket `job-artifacts` (private). RLS allows authenticated owner to read objects.

## Environment

Copy [`.env.example`](../.env.example) to `crm/.env.local` (or use root `.env` for monorepo).

| Variable | Client | Server | Notes |
|----------|--------|--------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | yes | yes | Required. Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | yes | yes | Required. Anon key (RLS) |
| `NEXT_PUBLIC_SITE_URL` | optional | optional | Override app origin; on Vercel auto-detects from `VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL` (localhost value is ignored on Vercel). Magic links return to the host the sign-in form was submitted on (any domain of this project on Vercel, local hosts, or this URL), so the PKCE cookie is found |
| `CRM_OWNER_EMAIL` | — | yes | Comma-separated allowlist; must match Supabase Auth user email(s) |
| `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY` | — | yes (server only) | Required (one of the two). Signed URLs for artifacts via `getArtifactSignedUrl` |
| `SUPABASE_STORAGE_BUCKET` | — | optional | Defaults to `job-artifacts` |
| `NEXT_PUBLIC_DEMO_MODE` | optional | optional | Shows the demo-data badge |

Variables are validated in `lib/env.ts`. When a required one is missing or invalid, the proxy answers every page request with `503` and the plain text "The app is not configured yet." The server log names the variables. Values are never logged or sent to the browser.

## Dev

```bash
cd crm
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — you will be redirected to `/login` until signed in.

`crm/.gitignore` un-ignores `lib/`, because some global gitignore files exclude it. The app keeps its source there.

Tests and fixtures use invented data only. Keep real names, emails and other personal details out of code, tests and this README.

## Security (no Vercel Deployment Protection required)

The publishable Supabase key is public in the browser bundle by design. Protection is in Postgres:

- Migration `005_crm_allowlist_rls.sql` enables RLS on `crm_owner_allowlist` and revokes API access — the owner gate cannot be rewritten via REST.
- Domain tables stay behind `crm_is_owner()` policies for `authenticated` only.
- `crm/proxy.ts` (Next.js 16 uses `proxy.ts` in place of `middleware.ts`) refreshes the session and enforces the `CRM_OWNER_EMAIL` check in `lib/supabase/session.ts`. That check is UI defense-in-depth only; RLS is the real control.
- Each response gets a per-request nonce CSP from `lib/csp.ts`. Scripts need the nonce (`x-nonce` is read by the root layout). Only the Supabase origin is allowed for images and connections. If you add an external origin, extend `buildContentSecurityPolicy` and check it still fits `frame-ancestors 'none'`.
- Security headers (HSTS, `nosniff`, referrer policy, `X-Frame-Options: DENY`, permissions policy) are defined once in `lib/security-headers.ts`. `next.config.ts` applies them to pages, and the proxy's 503 sets the same list. Changing a header changes it in both places.
- Artifact downloads use `getArtifactSignedUrl` in `lib/actions/artifacts.ts`. It checks the path, requires a signed-in owner, looks the file up in `artifacts` through the user's RLS client, and signs only the server's default bucket. The signed URL lasts 60 seconds.
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

# Supabase job tracker

This repo stores profile data, instructions, migrations, and Python tooling. Supabase stores job-search and freelance-project data.

## Setup

1. Create a Supabase project.
2. Create a private Storage bucket named `job-artifacts`.
3. Copy `.env.example` to `.env` and fill:
   - `SUPABASE_DB_URL` - use a Supabase Session Pooler connection string from Dashboard -> Connect. Do not use `db.<project-ref>.supabase.co` on networks without IPv6/outbound Postgres.
   - `SUPABASE_TEST_DB_URL` - local Supabase test database only; integration tests never fall back to production.
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY` for modern server-side Supabase API/Storage access, or `SUPABASE_SERVICE_ROLE_KEY` as a legacy fallback
   - `SUPABASE_STORAGE_BUCKET=job-artifacts`
4. Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

5. Apply migrations:

```bash
.venv/bin/python -m jobtracker migrate
```

## Direct DB connection

Use direct Python-to-Postgres communication for normal scripts:

```bash
.venv/bin/python -m jobtracker db-smoke
```

Expected production connection shape:

```text
postgresql://postgres.<project-ref>:<percent-encoded-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

The scripts disable prepared statements with `prepare_threshold=None`, so they stay compatible with Supavisor pooler modes.

Current temporary exception:

- The active Upwork automation playbook in `Docs/playbooks/UPWORK_EVALUATOR.md` uses Supabase MCP SQL for duplicate checks and run upserts because that path works inside the current sandbox while the direct pooler path does not.
- Keep the Python CLI and its direct-write code unchanged. It remains the preserved implementation for future re-enablement, and it still owns the richer path that uploads report artifacts to Supabase Storage.
- Until the direct path is re-enabled, the MCP path may leave `automation_runs.report_artifact_id` null and keep the local report path in run metadata instead.

If the smoke check says the pooler was reached but authentication failed, the host is correct and the database password in `.env` must be updated or reset in Supabase Dashboard. Percent-encode the password if it contains URL-special characters.

## Local integration tests

Write tests must use local Supabase only.

1. Install and start a Docker-compatible runtime such as OrbStack.
2. Start the local stack:

```bash
supabase start
```

3. Use the local DB URL from `supabase start` or `supabase status -o env`:

```bash
SUPABASE_TEST_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
  .venv/bin/python -m jobtracker db-smoke --test
```

4. Run the isolated DB integration test:

```bash
SUPABASE_TEST_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
  .venv/bin/python -m unittest tests.test_db_integration
```

`SUPABASE_TEST_DB_URL` must point to `127.0.0.1` or `localhost` and must not equal `SUPABASE_DB_URL`.

## Legacy import

The old Numbers export is semicolon-delimited despite the `.csv` extension.
If a same-name PDF export exists next to it, for example `Job search '25.pdf`, the importer reads clickable link annotations from the vacancy-link column, strips common tracking parameters, and uses those links to repair placeholder cells such as `Link`, `Link, link`, and `Link 1, link 2`.

Dry run:

```bash
.venv/bin/python -m jobtracker import-legacy --csv "Docs/Tracking/Job search '25.csv" --dry-run
```

To choose a specific PDF export:

```bash
.venv/bin/python -m jobtracker import-legacy \
  --csv "Docs/Tracking/Job search '25.csv" \
  --links-pdf "Docs/Tracking/Job search '25.pdf" \
  --dry-run
```

Import:

```bash
.venv/bin/python -m jobtracker import-legacy --csv "Docs/Tracking/Job search '25.csv"
```

The importer:

- skips rows without company names
- preserves the original row in metadata
- treats placeholder links like `Link` as unavailable when no PDF link is available
- stores cleaned URLs in opportunity/source-item metadata as `link_urls` and records whether they came from the CSV or PDF annotations
- can update existing rows if a later CSV/PDF export contains real URLs

## LinkedIn tracker import

LinkedIn tracker CSVs under `Docs/Tracking/` can be imported after the legacy history:

```bash
.venv/bin/python -m jobtracker import-linkedin-tracking --dry-run --as-of 2026-04-27
.venv/bin/python -m jobtracker import-linkedin-tracking --as-of 2026-04-27
```

By default this command reads:

- `Docs/Tracking/linkedin_jobs.csv`
- `Docs/Tracking/linkedin_applications_active.csv`
- `Docs/Tracking/linkedin_applications_archived.csv`

The importer:

- upserts evaluated jobs from `linkedin_jobs.csv` into `opportunities`, `source_items`, and `evaluations`
- upserts active LinkedIn applications into `applications`
- treats archived LinkedIn applications as declined jobs, with `applications.status = declined`, `current_stage = Declined`, and `outcome = declined`
- parses relative LinkedIn dates like `2mo ago` using the `--as-of` date
- strips tracking parameters and canonicalizes LinkedIn job URLs to `https://www.linkedin.com/jobs/view/<id>/`

## Greenhouse tracker import

Greenhouse application tracker data under `Docs/Tracking/greenhouse.csv` can be imported with:

```bash
.venv/bin/python -m jobtracker import-greenhouse --dry-run --as-of 2026-04-27
.venv/bin/python -m jobtracker import-greenhouse --as-of 2026-04-27
```

The importer:

- upserts Greenhouse application rows into `opportunities`, `source_items`, and `applications`
- stores Greenhouse application IDs as provider external IDs like `application:40658372`
- treats `posting_status = Inactive` as a declined application, with `applications.status = declined`, `current_stage = Declined`, and `outcome = declined`
- parses relative dates like `33 days ago` using the `--as-of` date
- strips tracking parameters from Greenhouse URLs

## Automation payloads

When the preserved direct CLI path is active, automations should produce a normalized JSON payload and call:

```bash
python3 -m jobtracker upsert-run \
  --provider linkedin \
  --payload /path/to/payload.json \
  --report /path/to/report.md
```

This DB-connected workflow is currently split:

- `Docs/playbooks/UPWORK_EVALUATOR.md` is allowed to use Supabase MCP SQL as the active sandbox-safe path for duplicate checks and run upserts.
- The Python CLI path remains preserved for future full re-enablement, especially for report-artifact upload through Supabase Storage.
- Other workflows should follow their own instruction files. Do not assume MCP writes are globally enabled unless the active instruction says so.

Minimum payload shape:

```json
{
  "run": {
    "run_key": "linkedin-2026-04-27",
    "started_at": "2026-04-27T08:30:00+02:00",
    "finished_at": "2026-04-27T08:35:00+02:00",
    "status": "completed",
    "summary": "3 jobs processed",
    "report_email_sent": true,
    "report_email_subject": "LinkedIn job triage - 2026-04-27 - 2 worth attention"
  },
  "source_items": [
    {
      "source_type": "email",
      "external_id": "gmail-message-id",
      "source_url": "https://mail.google.com/mail/#all/...",
      "timestamp": "2026-04-27T07:18:00Z",
      "subject": "LinkedIn Job Alert",
      "summary": "Email summary"
    }
  ],
  "opportunities": [
    {
      "opportunity_type": "employment",
      "external_id": "linkedin-job-id",
      "company": "Example Co",
      "title": "Senior iOS Engineer",
      "source_url": "https://www.linkedin.com/jobs/view/...",
      "apply_url": "https://example.com/apply",
      "location": "Barcelona",
      "work_model": "Hybrid",
      "domain": "FinTech",
      "evaluation": {
        "score": 8.5,
        "confidence": "High",
        "recommendation": "Apply",
        "priority": "P1",
        "main_match": "Strong SwiftUI and iOS architecture fit",
        "main_risks": "Salary not listed",
        "salary_expectation": "EUR 75k-85k",
        "action_next": "Apply today"
      }
    }
  ]
}
```

Upwork payloads use the same shape with `--provider upwork`, `opportunity_type: "freelance_project"`, `verdict`, `pricing_recommendation`, and `proposal_text` inside `evaluation`.

## Duplicate checks

Before reporting a job as new, check previous records:

```bash
python3 -m jobtracker check-duplicates \
  --provider linkedin \
  --company "Example Co" \
  --title "Senior iOS Engineer"
```

If a provider-specific ID is known:

```bash
python3 -m jobtracker check-duplicates --provider linkedin --external-id "4403780410"
```

## Data boundaries

- `Docs/Tracking/` is local/generated and ignored by git.
- Supabase Postgres is the source of truth for structured data.
- Supabase Storage is the source of truth for raw/long artifacts such as reports, transcripts, raw emails, and generated application materials.
- The schema keeps flexible `metadata jsonb` columns so new providers and fields can be added without breaking existing ingestion.

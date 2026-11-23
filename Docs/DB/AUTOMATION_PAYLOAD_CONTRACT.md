# Automation payload contract

`schemas/automation-payload.v1.schema.json` is the authoritative PAYLOAD-V1
definition. This page explains fields and workflow but does not override the schema.
Producers emit `run`, `source_items`, and `opportunities`. The validator reads legacy
top-level `emails` and `jobs` aliases with warnings and normalizes them to the
canonical names during the v0.2 compatibility window.

Automations should write a JSON payload that can be consumed by:

```bash
python3 -m jobtracker upsert-run --provider <provider> --payload payload.json --report report.md
```

Before DB sync, deterministic helpers should validate, normalize, and enrich the payload:

```bash
python3 -m jobtracker validate-payload --provider <provider> --payload payload.json --normalized-out payload.normalized.json
python3 -m jobtracker dedupe-candidates --provider <provider> --payload payload.normalized.json --payload-dir outputs/automation-payloads --output payload.deduped.json
```

For Upwork alert emails, build the opportunity packet from the deterministic email parser before evaluation:

```bash
python3 -m jobtracker parse-upwork-alerts --source-payload upwork-mail-source.payload.json --run-key upwork-YYYY-MM-DD-HHMM --output upwork-alerts.payload.json
```

## Top-level fields

- `run`: metadata about the automation run.
- `source_items`: emails, pages, imported rows, or other source records.
- `opportunities`: normalized jobs or freelance projects.
- `manual_review_blockers`: optional list of unresolved blockers.
- `summary`: optional run summary.

## Run fields

- `run_key`: stable unique key, for example `linkedin-2026-04-27`.
- `started_at`, `finished_at`: ISO timestamps.
- `status`: `completed`, `partial`, or `failed`.
- `summary`: short human summary.
- `report_email_sent`: boolean.
- `report_email_subject`: subject line sent to the configured report email (`JOBTRACKER_REPORT_EMAIL_TO`).

## Source item fields

- `source_type`: `email`, `job_page`, `ats_page`, `import_row`, `report`, or provider-specific text.
- `external_id`: Gmail message ID, LinkedIn job ID, Upwork job ID, ATS ID, or similar.
- `source_url`: Gmail/job/source URL.
- `timestamp`: source timestamp.
- `subject` or `title`.
- `summary` or `snippet`.
- `raw_text`: full source text. The PostgreSQL store keeps it only as `opportunity_texts` for opportunities selected by `store.text_retention` (default `shortlisted`); otherwise it keeps a SHA-256 and an excerpt.

## Opportunity fields

- `opportunity_type`: `employment` or `freelance_project`.
- `external_id`: provider-specific job/project ID.
- `company`: company/client name.
- `title`: role or project title.
- `source_url`: source job/project URL.
- `apply_url`: direct application URL when known.
- `location`, `work_model`, `engagement_type`, `seniority`, `domain`.
- `compensation_text`, `budget`, `currency`, `budget_type`.
- `metadata`: provider-specific extracted facts. Upwork email-derived candidates should include `extraction_method`, `source_fact_scope`, `page_enrichment_status`, parser confidence/missing fields, visible snippet, skills, and client economics.
- `evaluation`: nested evaluation object.
- `application`: optional nested application object when an actual application was made.
- `source_items`: optional source items specific to this opportunity. Entries may be full source-item objects or string references to top-level `source_items[].external_id`.
- `dedupe_status`: `new`, `exact_external_id`, `exact_company_title`, `same_company_recent_application`, or `recently_notified`.
- `dedupe_source`: configured `jobstore`, or `local_fallback_index` (payload history, used only with the SQLite store), or both.
- `dedupe_reasons`: deterministic reason codes used for the decision.
- `dedupe_matches`: compact evidence records for exact IDs, same-company applications, or recent notifications.
- `email_policy`: `include_detail` or `suppress_detail`.

## Evaluation fields

For employment jobs:

- `score`
- `confidence`
- `recommendation`
- `priority`
- `main_match`
- `main_risks`
- `missing_information`
- `positioning_angle`
- `salary_expectation`
- `action_next`
- `manual_review_reason`

For freelance projects:

- `verdict`
- `confidence`
- `pricing_recommendation`
- `main_match`
- `main_risks`
- `proposal_text`
- `action_next`
- `manual_review_reason`

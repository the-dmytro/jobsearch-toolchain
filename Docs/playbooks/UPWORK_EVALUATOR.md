# Codex instruction: Upwork job alert evaluator

Last updated: 2026-05-31

## Purpose

Evaluate Upwork job alert emails for {{OWNER_NAME}} and decide which postings are worth applying to right now, given both:

- real technical fit
- current Upwork-stage economics

This instruction is for screening jobs fast and pragmatically, updating Supabase as the source of truth, writing a Markdown report, and emailing {{OWNER_NAME}} a concise summary of jobs worth attention. Proposal material is produced only when a job is actually worth it.

## Codex automation usage

This instruction is designed to run from this repository in Codex:

- Workspace: `{{WORKSPACE_ROOT}}`
- Instruction file: `Docs/playbooks/UPWORK_EVALUATOR.md`
- DB tracker: deterministic `jobtracker` CLI helpers with direct Postgres when available; MCP only as a temporary fallback
- Markdown reports: `Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md`
- Source mail payload path: `outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-mail-source.payload.json`
- Transient payload path: `outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.payload.json`
- Report email recipient: `{{REPORT_EMAIL}}`

Suggested automation prompt:

```text
Run Docs/playbooks/UPWORK_EVALUATOR.md exactly as written.
```

Default automation cadence is twice daily. Correctness is based on mail-folder/source-item state, not on a fixed lookback window. The 14-hour mail lookback is only an overlap fallback when source state is unavailable. Scheduled runs must not fetch or browse Upwork job pages for enrichment, because Upwork page access is frequently blocked by Cloudflare and wastes run budget. If mail access, deterministic parsing, DB sync, email sending, or the workspace is unavailable, report the blocker clearly and do not invent missing data. If DB sync is unavailable, continue with the local payload and Markdown report as the fallback record for the run, and still send the report email if the evaluation work itself is complete.

## Source files in this project

Use these local Markdown files as source of truth, in this order:

1. `profile/CV_SOURCE.md`
2. `profile/00_PROJECT_INSTRUCTIONS.md`
3. `profile/01_PREFERENCES.md`
4. `profile/05_ROLE_TARGETS.md`
5. `profile/03_WORDS_AND_TONE.md`
6. `profile/04_LINKS_AND_CONTACTS.md`
7. `profile/02_COMPENSATION_RESEARCH.md`

Optional project context when relevant:

- `profile/06_PROJECT_SPOTLIGHTS.md`
- `profile/project-banks/protect_project_bank.md`
- `profile/project-banks/lloyd_project_bank.md`
- `profile/project-banks/wristcam_project_bank.md`

Do not reference old `/mnt/data` paths. Do not reference source files that do not exist in this repository.

The PDFs in `profile/cvs/` are output/reference artifacts, not the primary source of truth for this task unless {{OWNER_NAME}} explicitly asks to compare against a PDF.

## DB workflow

Use Supabase as the operational source of truth for seen projects, evaluations, and automation runs when it is available. Deterministic local payloads, source state, and reports are the fallback source of record until DB sync can be restored.

Active path for this instruction:

- Prefer deterministic CLI commands over prompt-written SQL.
- In Codex automation, invoke jobtracker commands directly with the `.venv/bin/python -m jobtracker ...` prefix shown below. Do not wrap these commands in `python3`, `/bin/zsh -lc`, shell substitutions, or redirections unless that exact wrapper command has been separately approved for automation permissions.
- At the start of the run, build the local fallback index:

```bash
.venv/bin/python -m jobtracker build-local-index --payload-dir outputs/automation-payloads
```

- If direct DB is expected to be available, test it once with:

```bash
.venv/bin/python -m jobtracker db-smoke --write-test
```

- After writing the payload, validate and normalize it:

```bash
.venv/bin/python -m jobtracker validate-payload --provider upwork --payload outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.payload.json --normalized-out outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.normalized.payload.json
```

- Run local fallback dedupe before deciding what to emphasize in the email:

```bash
.venv/bin/python -m jobtracker dedupe-candidates --provider upwork --payload outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.normalized.payload.json --payload-dir outputs/automation-payloads --include-db --output outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.deduped.payload.json
```

- Upsert the deduped payload through direct Postgres when `db-smoke --write-test` works:

```bash
.venv/bin/python -m jobtracker upsert-run --provider upwork --payload outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.deduped.payload.json --report Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md
```

- If DB sync fails, keep the payload/report and leave DB recovery to:

```bash
.venv/bin/python -m jobtracker sync-pending-runs --payload-dir outputs/automation-payloads --provider upwork
```

- Use Supabase MCP SQL only as an interactive emergency fallback when direct Postgres is unavailable and {{OWNER_NAME}} has not asked to pause the run.

Rules:

- Write a dated Markdown report under `Docs/Tracking/UpworkReports/`.
- Create the transient payload JSON under `outputs/automation-payloads/`. Create the directory if needed.
- Use the same `run_key` for the whole run. Format: `upwork-YYYY-MM-DD-HHMM`.
- Attempt to upsert the run once before sending the email with `report_email_sent = false`.
- After sending the email, update the same payload with final email fields and attempt to upsert the same `run_key` again. If dedupe must be rerun after an upsert, use the same `run_key`; `dedupe-candidates` excludes current-run-only DB matches so the run does not suppress itself.
- If the DB write fails, keep the payload file in `outputs/automation-payloads/`, treat the local payload plus Markdown report as the fallback record for the run, continue to the report email if the evaluation is otherwise complete, and mark the run `partial` unless another blocker makes it `failed`.

Active duplicate-check behavior:

- Normalize Upwork job IDs without the leading `~`.
- Run `dedupe-candidates --include-db` before the final report/email when DB is available and honor `email_policy = suppress_detail`.
- Prefer direct `check-duplicates` by normalized Upwork job ID when DB is available.
- When no reliable Upwork job ID is available, fall back to company/title matching.
- If DB is unavailable, use the local fallback index and mark `dedupe_source = local_fallback_index`. Do not claim a job is new unless neither DB nor local index found a match.

Direct DB commands:

```bash
.venv/bin/python -m jobtracker check-duplicates --provider upwork --external-id "<upwork_job_id>"
.venv/bin/python -m jobtracker check-duplicates --provider upwork --title "Example project title"
.venv/bin/python -m jobtracker upsert-run --provider upwork --payload outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.payload.json --report Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md
```

## Report files

For every completed run, write a report to:

`Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md`

Rules:

- Use local run date and 24-hour local time in the filename.
- Keep the report readable as a standalone artifact.
- Put `Apply` and `Apply cautiously` jobs first.
- Include skipped jobs, but keep skip analysis compact.
- Include direct Upwork job links and source email links when available.
- Keep long job descriptions out of the report. Use short excerpts or summaries.
- Do not write secrets, private email body dumps, or unnecessary personal data into the report.
- Register the run through the deterministic `.venv/bin/python -m jobtracker upsert-run` command when direct DB access is verified. If it is unavailable, keep the local Markdown report and payload on disk as the fallback record for the run and use `.venv/bin/python -m jobtracker sync-pending-runs` later.

## Payload requirements

The transient payload must contain:

- `run`
- `source_items`
- `opportunities`
- `manual_review_blockers`
- `summary`

`run` fields:

- `run_key`
- `started_at`
- `finished_at`
- `status`: `completed`, `partial`, or `failed`
- `summary`
- `report_email_sent`
- `report_email_subject`
- `source_items_count`
- `opportunities_count`
- `evaluations_count`
- `manual_review_count`

`source_items`:

- one record per Gmail message actually processed
- include `source_type`, `external_id`, `source_url`, `timestamp`, `subject`, and `summary`

`opportunities`:

- one record per distinct Upwork posting
- `opportunity_type` must be `freelance_project`
- include `external_id`, `title`, `source_url`, `apply_url`, `engagement_type`, and `source_items`
- `source_items` should reference the top-level Gmail `external_id` values for traceability

Each opportunity must include `evaluation` with:

- `verdict`: `Apply`, `Apply cautiously`, or `Skip`
- `confidence`
- `pricing_recommendation` when the job is worth attention
- `main_match`
- `main_risks`
- `proposal_text` when the job is worth attention
- `action_next`
- `manual_review_reason` when needed

Do not create `applications` rows for Upwork unless there is explicit evidence of a real submitted proposal or later workflow step that should be persisted as an application record.

## Report email

Send one concise report email to:

`{{REPORT_EMAIL}}`

This email is allowed by this instruction. Do not send any other emails or messages unless {{OWNER_NAME}} explicitly asks.

Subject format:

`Upwork job alerts - YYYY-MM-DD HH:MM - N worth attention`

If there are no `Apply` or `Apply cautiously` jobs, use:

`Upwork job alerts - YYYY-MM-DD HH:MM - no good matches`

Email body rules:

- Do not attach or paste the full Markdown report.
- Keep the email concise enough to read quickly on mobile.
- Include only `Apply` and `Apply cautiously` jobs by default.
- Include skipped jobs only as a one-line summary.
- For every job mentioned, include the direct Upwork job link.
- Include verdict, suggested pricing, job type, one main reason, one main risk, and next action.
- Include connects, budget, client quality, and hiring activity when available because those are critical Upwork economics.
- Do not paste full proposal text into the email.
- End with the local Markdown report path for extended details.

Email body structure:

```text
Hi {{OWNER_NAME}},

Upwork jobs worth attention:

1. Job title
   Verdict: Apply, confidence High
   Type/pricing: Hourly, suggest $X/hr
   Client/economics: payment verified, $X spent, Y proposals, Z connects
   Why: one short reason
   Risk: one short risk or "None obvious"
   Action: apply now / apply cautiously / review manually
   Job: URL

Skipped summary: 5 jobs skipped, mostly broad cross-platform work or weak economics.

Full report: Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md
```

If no jobs are worth attention, send a short email saying that no good matches were found, include counts and any manual review blockers.

## Truth rules

- Use only facts from the local source files, fetched mail content, deterministic parser output, and explicitly cited non-Upwork public information when it is already available in the source payload.
- Do not invent project details, stack details, metrics, client details, app links, Upwork client history, budgets, connects, or prior experience.
- If something important is missing, write `[NEEDS INPUT]`.
- If the job asks for experience that is not explicitly supported by the source files, treat that as a gap. Do not bluff.
- Keep email-derived facts separate from inference.
- When making an inference, say it is an inference.

## Hard action rules

- Do not apply to jobs.
- Do not send proposals.
- Do not message clients.
- Do not modify Upwork or other external accounts.
- Do not send emails other than the configured report email to `{{REPORT_EMAIL}}`.
- Do not commit or push report changes unless explicitly instructed.

## Tone and writing rules

- Professional, calm, direct, human
- Confident, but not inflated
- No buzzwords
- No em dashes
- Keep outputs concise
- Optimize for real client behavior and Upwork skim reading
- Use the local tone rules from `profile/03_WORDS_AND_TONE.md`

## User-specific Upwork strategy

Assume all of the following unless explicitly overridden in chat:

- {{OWNER_NAME}} is senior in reality, but still building his Upwork reputation
- strong reviews, clean delivery, and profile traction matter more than maximizing short-term income
- a lower-than-usual rate can be acceptable only when the opportunity is strategically good
- he must never be positioned as cheap labor
- position him as high-efficiency, low-risk, fast-to-unblock, and practical

## What counts as a good opportunity

Prefer jobs that are:

- clearly scoped
- concrete rather than generic
- active, with visible hiring momentum
- likely to end in a clean, successful delivery
- aligned with verified iOS strengths
- not too crowded for the connect cost
- technically meaningful but not chaos-heavy

Strong positive signals:

- narrow, specific problem
- hourly or tightly bounded first milestone
- credible client history
- visible interview or invite activity
- wording that suggests the client understands what they need
- realistic budget for the actual scope

Strong negative signals:

- vague generic iOS posts
- heavy design-led roles
- broad cross-platform roles
- highly niche specialties outside verified experience
- underpriced fixed-price work with broad scope
- new or weak client combined with fuzzy scope
- high proposal count with weak hiring activity
- requests that create legal or platform risk
- domains that conflict with preferences

## Hard domain constraints

Treat these as default rejects unless {{OWNER_NAME}} explicitly overrides:

- Gambling: skip
- Game development: skip unless explicitly relevant and desired
- Payday lending: skip
- Surveillance: skip

Treat these cautiously:

- crypto-only companies
- adult content, only if unlikely to harm long-term positioning

## Fit interpretation rules

Optimize for these lanes from the project sources:

- Senior iOS Engineer
- iOS Team Lead
- iOS Tech Lead
- Mobile Tech Lead only if clearly iOS-focused

Do not position {{OWNER_NAME}} as:

- Engineering Manager
- broad design specialist
- React Native lead unless the role explicitly asks and the available facts support mentioning the full-stack angle

## Daily workflow

### 1. Read local sources

Read the local source files listed above before evaluating jobs.

### 2. Fetch relevant Upwork mail

Fetch the Upwork mail folder first. Use the discovered top-level iCloud folder `Upwork` when present. Also accept `job/Upwork` and legacy Gmail-style folders `Jobs/Alerts/Upwork` and `Job/Alerts/Upwork`.

If IMAP helper credentials are configured, prefer:

```bash
.venv/bin/python -m jobtracker fetch-mail-folder --provider upwork --limit 50 --output outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-mail-source.payload.json
```

The Upwork folder may contain non-alert mail. Keep only messages that deterministically match Upwork job-alert or opportunity content by sender, subject, body text, or Upwork job links. Exclude report emails sent by this automation.

If IMAP is not configured, use the Gmail connector and search the Upwork alert label first. Search by sender/text only as a fallback. Search Gmail for the last 14 hours only when source-state history is unavailable or a recovery overlap is needed.

Include emails from:

- `upwork.com` senders
- `alerts@upwork.com`, if present
- `noreply@upwork.com`, if present
- any sender clearly related to Upwork job alerts

Include email types such as:

- saved search alerts
- recommended jobs
- new jobs matching profile
- invitations or direct job opportunities, if clearly job-related

Exclude forwarded copies from {{OWNER_NAME}}'s own email addresses unless the original Upwork email is not available. If forwarded emails are included, mark them as forwarded.

### 3. Parse postings deterministically from fetched emails

After fetching the mail-source payload, run the deterministic Upwork parser:

```bash
.venv/bin/python -m jobtracker parse-upwork-alerts --source-payload outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-mail-source.payload.json --run-key upwork-YYYY-MM-DD-HHMM --output outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.payload.json
```

Use the parser output as the authoritative candidate list. It must preserve one source item per processed email, dedupe repeated alert emails by normalized Upwork job ID, and keep extracted facts in each opportunity plus `metadata`.

The parser currently extracts:

- email subject, timestamp, and source message ID
- Upwork job ID and canonical job URL
- job title
- hourly or fixed-price compensation text
- estimated time, when visible
- posted date text, when visible
- visible description snippet
- skills/tags, when visible
- client economics line, including payment status, rating, spend, and country when present
- parser confidence and missing fields

Every parsed opportunity must include:

- `metadata.extraction_method = deterministic_upwork_email_parser`
- `metadata.source_fact_scope = email_derived`
- `metadata.page_enrichment_status = skipped_cloudflare_by_design`

If the parser reports missing cards or parser blockers, keep the source mail payload, mark the run `partial`, include the blocker in the report/email, and do not compensate with ad hoc LLM extraction or web scraping in the scheduled run. In a maintenance run, update the parser and tests from the saved source payload, then rerun the deterministic parse.

### 4. Evaluate from email-derived facts only

Scheduled automation must not inspect or fetch Upwork job pages. Direct Upwork links are kept for traceability and for {{OWNER_NAME}} to open manually, not for automation enrichment.

Use only the deterministic parser facts for:

- full job title
- job URL
- job type: hourly, fixed price, unclear, or mixed
- budget, hourly range, or fixed price
- connects cost, if visible
- client payment verification
- client spend, rating, hire count, location, and member age, if visible
- proposal count, interview count, invites sent, unanswered invites, if visible
- posted time and last viewed or interview activity, if visible
- project scope and likely deliverables
- required stack and platform requirements
- iOS-specific requirements
- non-iOS requirements and gaps
- special instructions from the client
- legal, platform, account-sharing, or publishing risks
- inaccessible or uncertain information

When a field is not present in the parsed email facts, mark it as unavailable rather than trying to infer it from an Upwork page. Connects, proposal count, interview count, invites, unanswered invites, and last-viewed activity are often unavailable from alert emails; treat them as missing unless the parser captured them explicitly.

### 5. Check duplicates in DB

Before reporting a project as new, check deterministic dedupe evidence:

- existing project rows with the same Upwork job ID
- existing or recent applications to the same company or same role family
- recent evaluations of the same title
- repeated alerts for the same job

Do not create duplicate project records for the same Upwork job ID.
Use `dedupe-candidates --include-db` when DB is available. Omit `--include-db` only when DB is down so the local fallback index can still run. Use direct DB `check-duplicates` for spot checks. Use MCP SQL only as a temporary fallback.

### 6. Judge the Upwork post

Evaluate all of the following:

1. fit with verified experience
2. probability of fast, successful delivery
3. chance of a satisfied client and a strong review
4. likelihood that the scope will stay controlled
5. client seriousness and readiness to move
6. whether the budget is acceptable for profile-building purposes
7. whether the post looks risky, chaotic, likely to expand unfairly, or likely to become support burden
8. whether the connect cost is justified by the odds

### 7. Produce one verdict per job

For each job link, produce exactly one of these verdicts:

- `Apply`
- `Apply cautiously`
- `Skip`

For `Skip`, keep it short and decisive.

For `Apply` or `Apply cautiously`, include:

- short explanation
- fit snapshot
- safest strategy
- pricing recommendation
- application strategy
- proposal text

### 8. Write the report and build the transient payload

Write the Markdown report under:

`Docs/Tracking/UpworkReports/YYYY-MM-DD-HHMM-upwork-alerts.md`

Write the transient payload JSON under:

`outputs/automation-payloads/YYYY-MM-DD-HHMM-upwork-alerts.payload.json`

Requirements:

- one top-level `run` object
- one `source_items` entry per processed Gmail email
- one `opportunities` entry per distinct job
- concise but useful `summary`
- `manual_review_blockers` list when relevant

For each Upwork opportunity, store the proposal text in `evaluation.proposal_text` only when the job is worth attention.

### 9. Upsert the run into Supabase

Before sending the email:

- write the payload with `report_email_sent = false`
- validate and normalize it with `validate-payload`
- enrich it with `dedupe-candidates --include-db` when DB is available
- attempt to upsert it through direct Postgres with `.venv/bin/python -m jobtracker upsert-run`
- if that upsert fails, record the blocker in the payload and report, keep the run moving, and treat the local report plus payload as the fallback record

After sending the email:

- update the same payload file with final `report_email_sent` and `report_email_subject`
- validate again if the payload changed; rerun dedupe only when opportunity content changed
- attempt to upsert the same `run_key` again through direct Postgres
- if the second upsert fails, keep the updated payload and report on disk and report that the email was sent but the DB sync is still pending

Required DB behavior for the upsert:

- upsert the `providers` row for `upwork`
- upsert the `automation_runs` row keyed by `run_key`
- delete prior `evaluations` rows for that `automation_run_id`
- upsert `source_items`
- upsert `organizations` and `opportunities`
- link source items to opportunities
- insert `evaluations`
- insert `applications` only when there is explicit evidence of a real submitted proposal or later application workflow step
- update `automation_runs.opportunities_count` and `automation_runs.evaluations_count` at the end of the transaction

### 10. Send the concise email

Send the concise email after the first DB upsert attempt. If that attempt fails, still send the email as long as Gmail access works and the evaluation itself is complete enough to produce a truthful report. DB failure alone must not block the report email.

If SMTP helper credentials are configured, prefer:

```bash
.venv/bin/python -m jobtracker send-report-email --provider upwork --run-key upwork-YYYY-MM-DD-HHMM --subject "Upwork job alerts - YYYY-MM-DD HH:MM - N worth attention" --body-file /path/to/email-body.txt
```

If SMTP is not configured, use the Gmail connector to send the allowed report email and record the sent state in the payload.

If email sending fails, keep the payload file and state the email failure in the final Codex response.

## Final Codex response format

Return a short message with:

- `run_key`
- whether the DB upsert succeeded
- whether the report email was sent
- number of emails processed
- number of jobs extracted
- Apply or Apply cautiously jobs worth attention
- manual review blockers
- today's action list

## Heuristics from prior evaluations

### Usually apply

- narrow technical problem
- visible hiring activity
- realistic hourly structure
- client looks real
- good chance of fast clean delivery
- connects are not excessive

### Usually apply cautiously

- decent technical fit but some scope ambiguity
- good client but crowded post
- acceptable rate for profile-building, not great
- solid opportunity if treated as selective or speculative

### Usually skip

- generic crowded iOS post with little specificity
- design-heavy or UI-design-first roles
- broad cross-platform roles
- specialized niche outside documented experience
- underpriced fixed-price builds
- risky publishing, legal, or account-sharing requests
- new weak client plus vague scope
- connect cost is too high relative to the odds

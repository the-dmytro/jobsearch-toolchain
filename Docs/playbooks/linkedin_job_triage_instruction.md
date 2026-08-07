# Codex instruction: LinkedIn job triage

Last updated: 2026-05-12

## Purpose

Run a LinkedIn job search triage for {{OWNER_NAME}}.

The job is to read LinkedIn job emails from Gmail, extract all job postings, research each role and company, compare them against {{OWNER_NAME}}'s confirmed profile and preferences, update Supabase as the source of truth, and email {{OWNER_NAME}} a concise summary of jobs worth attention.

## Codex automation usage

This instruction is designed to run from this repository in Codex:

- Workspace: `{{WORKSPACE_ROOT}}`
- Instruction file: `Docs/playbooks/linkedin_job_triage_instruction.md`
- DB tracker: Supabase through `.venv/bin/python -m jobtracker`
- Transient payload path: `outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.payload.json`
- Markdown report path: `Docs/Tracking/Reports/YYYY-MM-DD-linkedin-triage.md`
- Report email recipient: `{{REPORT_EMAIL}}`

Suggested automation prompt:

```text
Run Docs/playbooks/linkedin_job_triage_instruction.md exactly as written.
```

Default automation cadence is daily. Correctness is based on Gmail label/source-item state, not on a fixed 24 to 48 hour window. The 24 to 48 hour Gmail search is only an overlap fallback when source state is unavailable. If the automation cannot access Gmail, web research, or the workspace, report the blocker clearly and do not invent missing data. If the DB connection is unavailable, continue with local payload and Markdown report artifacts as the fallback record for the run, and still send the report email if the evaluation work itself is complete.

## Source files in this project

Use only these local Markdown files as source of truth for {{OWNER_NAME}}'s profile, preferences, compensation, tone, and project facts:

- `profile/00_PROJECT_INSTRUCTIONS.md`
- `profile/01_PREFERENCES.md`
- `profile/02_COMPENSATION_RESEARCH.md`
- `profile/03_WORDS_AND_TONE.md`
- `profile/04_LINKS_AND_CONTACTS.md`
- `profile/05_ROLE_TARGETS.md`
- `profile/06_PROJECT_SPOTLIGHTS.md`
- `profile/CV_SOURCE.md`
- `profile/project-banks/lloyd_project_bank.md`
- `profile/project-banks/protect_project_bank.md`
- `profile/project-banks/wristcam_project_bank.md`

Do not reference old `/mnt/data` paths. Do not reference source files that do not exist in this repository.

The PDFs in `profile/cvs/` are output/reference artifacts, not the primary source of truth for this task unless {{OWNER_NAME}} explicitly asks to compare against a PDF.

## DB workflow

Use Supabase as the operational source of truth for seen roles, prior applications, evaluations, and automation runs when it is available. If Supabase reads or writes fail, the local payload plus Markdown report become the fallback source of record for that run until the DB path is restored.

Rules:

- Do not update `Docs/Tracking/linkedin_jobs.csv` during this workflow. Treat it as historical local material that has already been imported into the DB.
- Write a Markdown report for this workflow under `Docs/Tracking/Reports/YYYY-MM-DD-linkedin-triage.md`.
- Create the transient payload JSON under `outputs/automation-payloads/`. Create the directory if needed.
- Use the same `run_key` for the whole run. Format: `linkedin-YYYY-MM-DD`.
- Attempt to upsert the run once before sending the email with `report_email_sent = false`.
- After sending the email, update the same payload with final email fields and attempt to upsert the same `run_key` again.
- If the DB write fails, keep the payload file in `outputs/automation-payloads/`, treat the local payload plus Markdown report as the fallback record for the run, continue to the report email if the evaluation is otherwise complete, and mark the run `partial` unless another blocker makes it `failed`.
- Use `.venv/bin/python -m jobtracker` for DB reads and writes.
- In Codex automation, invoke jobtracker commands directly with the `.venv/bin/python -m jobtracker ...` prefix shown below. Do not wrap these commands in `python3`, `/bin/zsh -lc`, shell substitutions, or redirections unless that exact wrapper command has been separately approved for automation permissions.
- Prefer deterministic helper commands over prompt-written SQL or ad hoc duplicate reasoning.

At the start of the run, build the local fallback index:

```bash
.venv/bin/python -m jobtracker build-local-index --payload-dir outputs/automation-payloads
```

If direct DB is expected to be available, test it once with:

```bash
.venv/bin/python -m jobtracker db-smoke --write-test
```

Read commands:

```bash
.venv/bin/python -m jobtracker check-duplicates --provider linkedin --external-id "<linkedin_job_id>"
```

Fallback duplicate check when no reliable LinkedIn job ID is available:

```bash
.venv/bin/python -m jobtracker check-duplicates --provider linkedin --company "Example Co" --title "Senior iOS Engineer"
```

Write command:

```bash
.venv/bin/python -m jobtracker upsert-run --provider linkedin --payload outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.payload.json
```

Before every upsert, validate/normalize and enrich the payload:

```bash
.venv/bin/python -m jobtracker validate-payload --provider linkedin --payload outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.payload.json --normalized-out outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.normalized.payload.json
.venv/bin/python -m jobtracker dedupe-candidates --provider linkedin --payload outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.normalized.payload.json --payload-dir outputs/automation-payloads --include-db --output outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.deduped.payload.json
.venv/bin/python -m jobtracker upsert-run --provider linkedin --payload outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.deduped.payload.json --report Docs/Tracking/Reports/YYYY-MM-DD-linkedin-triage.md
```

If DB sync fails, keep the deduped payload/report and recover later with:

```bash
.venv/bin/python -m jobtracker sync-pending-runs --payload-dir outputs/automation-payloads --provider linkedin
```

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

- one record per distinct job posting
- `opportunity_type` must be `employment`
- include `external_id`, `company`, `title`, `source_url`, `apply_url`, `location`, `work_model`, `employment_type`, `seniority`, `domain`, and `source_items`
- `source_items` should reference the top-level Gmail `external_id` values for traceability

Each opportunity must include `evaluation` with:

- `score`
- `confidence`
- `recommendation`: `Apply`, `Maybe`, `Skip`, or `Manual review needed`
- `priority`: `P1`, `P2`, `P3`, or `Skip`
- `main_match`
- `main_risks`
- `missing_information`
- `positioning_angle`
- `salary_expectation`
- `action_next`
- `manual_review_reason` when needed

Only include an `application` object if the run has explicit evidence that {{OWNER_NAME}} actually applied during or before the run and that fact needs to be written now.

## Report email

Send one concise report email to:

`{{REPORT_EMAIL}}`

This email is allowed by this instruction. Do not send any other emails or messages unless {{OWNER_NAME}} explicitly asks.

Subject format:

`LinkedIn job triage - YYYY-MM-DD - N worth attention`

If there are no P1 or P2 jobs, use:

`LinkedIn job triage - YYYY-MM-DD - no strong matches`

Email body rules:

- Do not attach or paste a Markdown report.
- Keep the email concise enough to read quickly on mobile.
- Include only P1 and P2 jobs by default.
- Include P3 jobs only when there are no P1 or P2 jobs and a P3 role may still be strategically useful.
- Do not include full skipped-job details. Summarize skips in one line.
- For every job mentioned, include direct links needed to act:
  - application link, if available
  - LinkedIn job link or job post link
  - company or careers link when it is the best application route
- Use visible URLs even if the email client does not preserve hyperlink formatting.
- Include salary expectation, location or work model, score, recommendation, one main reason, one main risk, and next action.
- Mention manual review blockers only when they affect a job worth attention.

Email body structure:

```text
Hi {{OWNER_NAME}},

Jobs worth attention today:

1. Company - Role
   Priority: P1, score 8.5/10, confidence High
   Location/work model: Barcelona hybrid
   Salary expectation: EUR X-Y
   Why: one short reason
   Risk: one short risk or "None obvious"
   Action: apply today / review manually / wait
   Apply: URL
   Job post: URL

Maybe:
- Company - Role, P2, score 7.5/10
  Action: review work model before applying
  Apply: URL

Skipped summary: 4 roles skipped, mostly Android-heavy or off-target seniority.
```

If no jobs are worth attention, send a short email saying that no strong matches were found, include counts and any manual review blockers.

## Hard rules

- Use only facts about {{OWNER_NAME}} that appear in the project files above or were explicitly provided by him.
- Do not invent metrics, responsibilities, skills, titles, team size, company details, outcomes, or personal facts.
- If something important is unknown, write `[NEEDS INPUT]`.
- Do not use, recommend, or cite Russian resources.
- Do not apply to jobs, send messages, send emails other than the configured report email to `{{REPORT_EMAIL}}`, or modify external accounts unless explicitly instructed.
- Do not commit or push tracker changes unless explicitly instructed.
- Do not recommend Engineering Manager roles.
- Mention full-stack experience only when the job explicitly asks for it.
- Keep final writing clear, direct, calm, human, and professional.
- Avoid hype, buzzwords, and em dashes.

## Daily workflow

### 1. Read local sources

Read the local source files listed above.

### 2. Fetch relevant Gmail emails

Fetch the LinkedIn mail folder first. Use the discovered iCloud folder `job/LinkedIn` when present. Also accept legacy Gmail-style folders `Jobs/Alerts/LinkedIn` and `Job/Alerts/LinkedIn`.

If IMAP helper credentials are configured, prefer:

```bash
.venv/bin/python -m jobtracker fetch-mail-folder --provider linkedin --limit 50 --output outputs/automation-payloads/YYYY-MM-DD-linkedin-mail-source.payload.json
```

The LinkedIn folder may contain non-alert mail. Keep only messages that deterministically match LinkedIn job-alert or opportunity content by sender, subject, body text, or LinkedIn job links. Exclude security, password, and report emails.

If IMAP is not configured, use the Gmail connector and search the LinkedIn alert label first. Search by sender/text only as a fallback. Search Gmail for the last 24 to 48 hours only when source-state history is unavailable or a recovery overlap is needed.

Include emails from:

- `jobalerts-noreply@linkedin.com`
- `jobs-listings@linkedin.com`
- `jobs-noreply@linkedin.com`
- any other LinkedIn sender clearly related to jobs

Include email types such as:

- LinkedIn Job Alerts
- Top job picks
- "You may be a fit"
- "New jobs similar to..."
- saved job reminders
- recruiter or company alerts if clearly job-related

Exclude forwarded copies from {{OWNER_NAME}}'s own email addresses unless the original LinkedIn email is not available. If forwarded emails are included, mark `forwarded` as `yes`.

### 3. Extract all postings from each email

For every email, keep it separate.

For each email, extract:

- email subject
- sender
- timestamp
- email type
- Gmail link if available
- all visible job postings
- all LinkedIn job IDs
- all job titles
- company names
- locations
- work models
- posted dates, if present
- snippets or short description text from the email
- whether the email body was complete or clipped
- any missing fields

Keep email-derived facts separate from researched facts. Do not merge them silently.

### 4. Research each job

For each extracted job posting, research current information using primary sources first:

- LinkedIn job page, if accessible
- company career page
- official job post or ATS page
- company website
- reputable company profiles
- salary or compensation sources where relevant

For each role, gather:

- full job title
- company
- product or team, if available
- location and work model
- employment type
- seniority level
- stack and technologies
- iOS-specific requirements
- Android or cross-platform requirements, if any
- leadership or mentoring expectations
- product or domain context
- salary range, if listed
- benefits and equity, if listed
- language requirements
- work authorization or country restrictions
- application route
- source links
- inaccessible or uncertain information

If the exact LinkedIn job ID cannot be researched, search by title plus company plus location. If only a similar posting is found, label it `similar_posting_exact_id_not_confirmed`.

### 5. Check duplicates and prior applications

Before recommending a role as new, check deterministic dedupe evidence for:

- existing opportunity rows
- prior applications
- recent declines
- similar postings at the same company
- manual-review history
- recent recommendation emails for the same role

When a company appears again:

- say whether {{OWNER_NAME}} has already applied there, if known from the DB
- say whether the role is the same, similar, or meaningfully different
- recommend whether to apply, wait, or avoid duplicate effort
- do not mark a role as applied unless there is explicit evidence

Use `dedupe-candidates --include-db` when DB is available. Omit `--include-db` only when DB is down so the local fallback index can still run. If DB is unavailable, mark `dedupe_source = local_fallback_index` and do not claim that a role is new unless the local fallback index found no match.

### 6. Compare with {{OWNER_NAME}}'s profile

Score each job against {{OWNER_NAME}}'s confirmed profile and preferences.

Use these criteria:

- Role fit: Senior iOS Engineer, iOS Team Lead, iOS Tech Lead, Staff iOS Engineer, Mobile Tech Lead if iOS-focused
- Seniority fit: avoid mid-level or generic mobile roles unless strategically useful
- iOS depth: Swift, SwiftUI, UIKit, Objective-C, Combine, Core Data, Swift Concurrency, watchOS, architecture, testing
- Domain fit: communications, multimedia, streaming, AI, FinTech, health, sport, wellbeing, safety, digital safety, automotive
- Company fit: product company preferred, bigger company preferred, systems over chaos
- Work model fit: Barcelona hybrid or remote-first preferred
- Compensation fit: compare with `profile/02_COMPENSATION_RESEARCH.md` and current salary evidence when useful
- Dealbreakers: skip gambling, game development, payday lending, surveillance, and be cautious with crypto-only companies
- Language fit: English-friendly preferred, Spanish-only roles are weaker
- Application history: lower priority if already applied recently, unless this is a clearly different role

Do not infer that {{OWNER_NAME}} has Android, Kotlin, Java, RxSwift, MAUI, React Native, backend, or management experience unless the project files confirm it. If a role asks for a skill not confirmed, mark it as a gap or `[NEEDS INPUT]`.

### 7. Score and rank

Give every job:

- score from 1 to 10
- confidence: High, Medium, Low
- recommendation: Apply, Maybe, Skip, Manual review needed
- application priority: P1, P2, P3, Skip
- salary expectation: practical range and suggested ask
- main match reasons
- main risks
- missing information
- suggested positioning angle

Scoring guide:

- 9 to 10: strong target role, strong company or domain or work model, seniority and salary likely aligned
- 7 to 8.5: worth applying if details are acceptable
- 5 to 6.5: maybe, only if there is a specific strategic reason
- below 5: skip unless {{OWNER_NAME}} explicitly wants to pursue it

### 8. Salary expectations

Use `profile/02_COMPENSATION_RESEARCH.md` first, then supplement with current web research when useful.

Give salary expectations as:

- suggested ask
- practical range
- minimum worth considering
- notes on base vs total compensation when relevant

For Barcelona Senior iOS roles, use the Barcelona senior range as baseline. For lead or tech lead roles, use the lead scope range. For remote-first EU or US or EOR roles, allow higher expectations. For mid-level or mixed iOS and Android roles, lower the range and mark the tradeoff clearly.

### 9. Build the transient payload

Write the transient payload JSON under:

`outputs/automation-payloads/YYYY-MM-DD-linkedin-triage.payload.json`

Requirements:

- one top-level `run` object
- one `source_items` entry per processed Gmail email
- one `opportunities` entry per distinct job
- concise but useful `summary`
- `manual_review_blockers` list when relevant

### 10. Write the Markdown report

Write a Markdown report under:

`Docs/Tracking/Reports/YYYY-MM-DD-linkedin-triage.md`

The report should stay concise but useful. Include:

- emails processed
- extracted postings
- research results by role
- ranked recommendations
- manual review blockers
- today's action list

Do not attach or paste this Markdown report into the email. It is a local artifact for project history and review.
If the DB upsert path fails, this Markdown report and the payload file are the fallback record for the run.

### 11. Upsert the run into Supabase

Before sending the email:

- write the payload with `report_email_sent = false`
- validate and normalize it with `validate-payload`
- enrich it with `dedupe-candidates --include-db` when DB is available
- attempt to upsert the deduped payload with `.venv/bin/python -m jobtracker upsert-run --provider linkedin --payload <payload> --report <report>`
- if that upsert fails, record the blocker in the payload and report, keep the run moving, and treat the local report plus payload as the fallback record

After sending the email:

- update the same payload file with final `report_email_sent` and `report_email_subject`
- validate again if the payload changed; rerun dedupe only when opportunity content changed. If dedupe is rerun after an upsert, keep the same `run_key`; `dedupe-candidates` excludes current-run-only DB matches so the run does not suppress itself.
- attempt to upsert the same `run_key` again
- if the second upsert fails, keep the updated payload and report on disk and report that the email was sent but the DB sync is still pending

### 12. Send the concise email

Before sending, make sure every role in the email has the best available action link. Prefer an official application URL, then the LinkedIn job URL, then the company careers URL. If no reliable application link is available, write `[NEEDS INPUT]` and include the manual review reason.

Send the report email even if the DB upsert failed, as long as Gmail access works and the evaluation itself is complete enough to produce a truthful report. DB failure alone must not block the report email.

If SMTP helper credentials are configured, prefer:

```bash
.venv/bin/python -m jobtracker send-report-email --provider linkedin --run-key linkedin-YYYY-MM-DD --subject "LinkedIn job triage - YYYY-MM-DD - N worth attention" --body-file /path/to/email-body.txt
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
- P1 and P2 jobs worth attention
- manual review blockers
- today's action list

## Output style

Use labels like:

- `Email-derived`
- `Web-derived`
- `Inference`
- `Unavailable`
- `Needs manual review`

Keep the work concise but useful. Prefer direct judgments. Avoid generic advice.

When making an inference, say it is an inference.

Do not overstate confidence. If only a similar posting was found, say so.

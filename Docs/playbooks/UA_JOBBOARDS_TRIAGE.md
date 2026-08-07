# Codex instruction: DOU / Work.ua / Djinni jobboard triage

Last updated: 2026-06-04

## Purpose

Run a DOU, Work.ua, and Djinni job search triage for {{OWNER_NAME}}.

This workflow is intentionally the same operational flow as `Docs/playbooks/linkedin_job_triage_instruction.md`: use deterministic helper commands for source collection, payload normalization, dedupe, DB work, and email sending; use the LLM only for judgment work such as profile comparison, evaluation, ranking, report writing, and concise email writing.

The only designed difference from LinkedIn is the source stage:

- LinkedIn parses job-alert emails.
- This workflow searches DOU, Work.ua, and Djinni directly through deterministic collectors.

Supported profiles:

- `ios`: iOS/macOS roles.
- `data-ml-ai`: Data/ML/AI roles.

## Codex automation usage

This instruction is designed to run from this repository in Codex:

- Workspace: `{{WORKSPACE_ROOT}}`
- Instruction file: `Docs/playbooks/UA_JOBBOARDS_TRIAGE.md`
- DB tracker: Supabase through `.venv/bin/python -m jobtracker`
- Transient payload path: `outputs/automation-payloads/YYYY-MM-DD-<profile-output>-<provider>.*.payload.json`
- Manifest path: `outputs/automation-payloads/YYYY-MM-DD-<profile-output>-manifest.json`
- Markdown report path: from `manifest.artifacts.report_path`
- Report email recipient: `{{REPORT_EMAIL}}`

Suggested automation prompts:

```text
Run Docs/playbooks/UA_JOBBOARDS_TRIAGE.md exactly as written for profile ios.
```

```text
Run Docs/playbooks/UA_JOBBOARDS_TRIAGE.md exactly as written for profile data-ml-ai.
```

Default automation cadence must match the daily LinkedIn job triage automation: daily at 02:30 local automation time.

If DOU, Work.ua, Djinni, Supabase, SMTP, or the workspace is unavailable, report the blocker clearly and do not invent missing data. If the DB connection is unavailable, continue with local payload and Markdown report artifacts as the fallback record for that run, and still send the report email if the evaluation work itself is complete.

## Source files in this project

Read the profile files listed in the manifest under `profile.profile_files`. Use only those local files plus explicit user instructions as source of truth for {{OWNER_NAME}}'s profile, preferences, compensation, tone, and project facts.

Do not reference old `/mnt/data` paths. Do not reference source files that do not exist in this repository. The PDFs in `profile/cvs/` are output/reference artifacts, not the primary source of truth unless {{OWNER_NAME}} explicitly asks to compare against a PDF.

## DB workflow

Use Supabase as the operational source of truth for seen roles, prior applications, evaluations, and automation runs when it is available. If Supabase reads or writes fail, the local manifest, evaluated payloads, and Markdown report become the fallback source of record for that run until the DB path is restored.

Rules:

- Do not update historical CSV files during this workflow.
- Write the Markdown report to `manifest.artifacts.report_path`.
- Create all transient payload JSON files under `outputs/automation-payloads/`.
- Use stable daily run keys so retries update the same records:
  - iOS manifest run key: `ua-jobboards-YYYY-MM-DD`
  - Data/ML/AI manifest run key: `data-ml-ai-jobboards-YYYY-MM-DD`
  - provider run keys: `<provider>-<profile-output>-YYYY-MM-DD`
- Attempt to upsert every provider run once before sending the email with `report_email_sent = false`.
- After sending the email, update the same evaluated payloads with final email fields and upsert the same provider run keys again.
- If a DB write fails, keep the evaluated payloads and report, continue to the report email if evaluation is otherwise complete, and mark the affected run `partial` unless another blocker makes it `failed`.
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

Then prepare the jobboard run:

```bash
.venv/bin/python -m jobtracker prepare-jobboard-run --profile <ios|data-ml-ai>
```

The command prints the manifest JSON. Use `manifest_path` from stdout as the durable manifest path.

If DB sync fails after local artifacts are created, keep the evaluated payloads/report and recover later with:

```bash
.venv/bin/python -m jobtracker sync-pending-runs --payload-dir outputs/automation-payloads --provider <provider>
```

## Payload requirements

Every provider payload must contain:

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

- one record per job posting source collected from DOU, Work.ua, or Djinni
- include `source_type`, `external_id`, `source_url`, `timestamp`, `title`, `summary`, and available raw/detail text

`opportunities`:

- one record per distinct job posting
- `opportunity_type` must be `employment`
- include `external_id`, `company`, `title`, `source_url`, `apply_url`, `location`, `work_model`, `employment_type` or `engagement_type`, `seniority`, `domain` when known, and `source_items`
- `source_items` should reference the top-level job posting source item IDs for traceability

Each opportunity must include `evaluation` with:

- `score`
- `confidence`
- `recommendation`: `Apply`, `Maybe`, `Skip`, or `Manual review needed`
- `priority`: `P1`, `P2`, `P3`, or `Skip`
- `section`: `main`, `spare`, or `skip`
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

`<manifest.email.subject_prefix> - YYYY-MM-DD - N worth attention`

If there are no P1 or P2 jobs, use:

`<manifest.email.subject_prefix> - YYYY-MM-DD - no strong matches`

Email body rules:

- Do not attach or paste a Markdown report.
- Keep the email concise enough to read quickly on mobile.
- Include only P1 and P2 main roles by default.
- Include spare roles in a short separate section at the bottom.
- Include P3 roles only when there are no P1 or P2 jobs and a P3 role may still be strategically useful.
- Do not include full skipped-job details. Summarize skips in one line.
- For every job mentioned, include direct visible URLs needed to act.
- Include salary expectation, location or work model, score, recommendation, one main reason, one main risk, and next action.
- Mention manual review blockers only when they affect a job worth attention.

If no jobs are worth attention, send a short email saying that no strong matches were found, include counts and any manual review blockers.

## Hard rules

- Use only facts about {{OWNER_NAME}} that appear in the project files listed by the manifest or were explicitly provided by him.
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

Read the profile files listed in the manifest after running `prepare-jobboard-run`.

### 2. Search jobboards deterministically

Run:

```bash
.venv/bin/python -m jobtracker build-local-index --payload-dir outputs/automation-payloads
.venv/bin/python -m jobtracker db-smoke --write-test
.venv/bin/python -m jobtracker prepare-jobboard-run --profile <ios|data-ml-ai>
```

`prepare-jobboard-run` replaces LinkedIn's Gmail-fetch and email-extraction steps. It searches DOU, Work.ua, and Djinni directly, fetches available listing/detail data, validates payload shape, and enriches local/DB duplicate evidence.

Do not manually browse or scrape DOU, Work.ua, or Djinni unless the deterministic command fails and the failure itself is being investigated.

### 3. Evaluate each job

Evaluate only opportunities from each `provider_runs[].deduped_payload_path`.

Preserve deterministic fields. Add `evaluation` to every opportunity. Keep listing-derived facts separate from inference in the evaluation text when relevant.

Remote filter:

- Recommend only postings with explicit remote availability.
- If a posting is hybrid-only, office-only, location-tied, or remote availability is unclear, set `section = skip`.

Middle/lower-level handling:

- For `ios`, middle-level roles can be spare lower-effort variants, not main recommendations.
- For `data-ml-ai`, junior/middle bridge roles can be spare variants when they create useful AI/data experience, not main recommendations.

### 4. Score and rank

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

- 9 to 10: strong target role, strong company/domain/work model, seniority and compensation likely aligned
- 7 to 8.5: worth applying if details are acceptable
- 5 to 6.5: maybe or spare, only if there is a specific strategic reason
- below 5: skip unless {{OWNER_NAME}} explicitly wants to pursue it

### 5. Write evaluated payloads

For each provider, write an evaluated payload next to the deduped payload by replacing `.deduped.payload.json` with `.evaluated.payload.json`.

Before every upsert, validate and normalize:

```bash
.venv/bin/python -m jobtracker validate-payload --provider <provider> --payload <evaluated.payload.json> --normalized-out <evaluated.normalized.payload.json>
```

Use the normalized evaluated payload for DB upserts.

### 6. Write the Markdown report

Write the report to `manifest.artifacts.report_path`.

Include:

- profile and run summary
- provider counts and blockers
- main remote roles worth attention
- spare lower-effort or bridge variants at the bottom
- skipped summary
- recommended application order
- positioning notes
- manual review points

Do not attach or paste this Markdown report into the email.

### 7. Upsert before sending email

Before sending the email:

- keep `report_email_sent = false` in every evaluated provider payload
- set `evaluations_count` to the number of opportunities with evaluation
- validate and normalize every evaluated provider payload
- upsert every provider run with the same report:

```bash
.venv/bin/python -m jobtracker upsert-run --provider <provider> --payload <evaluated.normalized.payload.json> --report <report.md>
```

If an upsert fails, record the blocker in the payload/report, keep the run moving, and treat local artifacts as the fallback record.

### 8. Send the concise email

Before sending, make sure every role in the email has the best available action link. Prefer the job post URL from the provider payload unless a better official application URL is available.

Send the report email even if the DB upsert failed, as long as the evaluation itself is complete enough to produce a truthful report. DB failure alone must not block the report email.

If SMTP helper credentials are configured, prefer:

```bash
.venv/bin/python -m jobtracker send-report-email --provider jobboards-<profile> --run-key <manifest-run-key> --subject "<subject>" --body-file <email-body-path>
```

If SMTP is not configured, use the Gmail connector to send the allowed report email and record the sent state in the payload.

If email sending fails, keep the payload file and state the email failure in the final Codex response.

### 9. Upsert final sent state

After sending the email:

- update the same evaluated payload files with `report_email_sent = true`
- set `report_email_subject = <subject>`
- validate again
- upsert the same provider run keys again with the same report

If the second upsert fails, keep the updated payloads/report on disk and report that the email was sent but DB sync is still pending.

## Final Codex response format

Return a short message with:

- profile
- manifest run key
- whether DB upsert succeeded
- whether the report email was sent
- number of jobs collected
- P1 and P2 jobs worth attention
- spare roles count
- manual review blockers
- today's action list

## Output style

Use labels like:

- `Provider-derived`
- `Inference`
- `Unavailable`
- `Needs manual review`

Keep the work concise but useful. Prefer direct judgments. Avoid generic advice.

When making an inference, say it is an inference. Do not overstate confidence.

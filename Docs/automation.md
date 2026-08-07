# Automation

## Pipelines

Define pipelines in `config/jobsearch.toml`:

```toml
[[pipelines]]
name = "jobboards"
profile = "ios"
sources = ["dou", "workua", "djinni"]
notify = ["email"]
```

Run:

```bash
python -m jobtracker run jobboards
python -m jobtracker run jobboards --dry-run --fixture-dir jobtracker/fixtures/provider-fetch
```

Pipeline steps: **source → dedupe → store → notify**

## Manual commands

| Command | Purpose |
|---------|---------|
| `fetch-dou` / `fetch-workua` / `fetch-djinni` / `fetch-greenhouse-jobs` | Single-source discovery |
| `fetch-mail-folder --provider upwork` | IMAP fetch |
| `parse-upwork-alerts` | Deterministic email parse |
| `upsert-run --payload ...` | Persist automation payload |
| `send-report-email` | SMTP report with idempotency |
| `prepare-jobboard-run` | Multi-board triage manifest |

## Agent playbooks

DB-first automation instructions for AI agents:

- [LinkedIn triage](../Docs/playbooks/linkedin_job_triage_instruction.md)
- [Upwork evaluator](../Docs/playbooks/UPWORK_EVALUATOR.md)
- [UA job boards](../Docs/playbooks/UA_JOBBOARDS_TRIAGE.md)
- [Gmail setup](../Docs/playbooks/GMAIL_JOB_EMAIL_SETUP.md)

Playbooks reference `profile/` files and `{{REPORT_EMAIL}}` — fill templates before use.

## Scheduling examples

- [cron.example](../examples/automation/cron.example)
- [launchd.example.plist](../examples/automation/launchd.example.plist)
- [github-actions.example.yml](../examples/automation/github-actions.example.yml)

## Payload contract

All automation runs produce JSON matching [AUTOMATION_PAYLOAD_CONTRACT.md](../Docs/DB/AUTOMATION_PAYLOAD_CONTRACT.md). Validate before upsert:

```bash
python -m jobtracker validate-payload --provider upwork --payload outputs/automation-payloads/run.payload.json
```

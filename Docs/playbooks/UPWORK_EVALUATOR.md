# Agent playbook: Upwork alert evaluation

Use this only after the user selects Upwork and configures a mail inbox/parser or supplies exported messages. Do not assume a role, rate, availability, proposal style, or automation cadence.

Source-of-truth order:

1. Filled private files listed by the configured profile.
2. Deterministically parsed Upwork alert content.
3. Explicit instructions in the current task.

Ask for missing business constraints. Scheduled runs must not browse blocked Upwork pages merely to enrich an alert; retain the source item and mark missing fields for review.

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker fetch-mail-folder --provider upwork --output outputs/automation-payloads/upwork-mail.payload.json
.venv/bin/python -m jobtracker validate-payload --provider upwork --payload outputs/automation-payloads/upwork-mail.payload.json
.venv/bin/python -m jobtracker dedupe-candidates --provider upwork --payload outputs/automation-payloads/upwork-mail.payload.json --payload-dir outputs/automation-payloads --output outputs/automation-payloads/upwork-mail.deduped.payload.json
.venv/bin/python -m jobtracker upsert-run --provider upwork --payload outputs/automation-payloads/upwork-mail.deduped.payload.json
```

The commands use the configured store. Local artifacts remain the recovery boundary if optional PostgreSQL, mail sending, or notifications fail.

For each opportunity, separate verified fit, constraint conflicts, unknowns, and recommendation. Draft proposal material only when requested. Do not invent portfolio examples, outcomes, identity, rates, or availability.

Report message count, parsed opportunities, duplicates, recommendations, persisted run key, artifact paths, and action-required blockers.

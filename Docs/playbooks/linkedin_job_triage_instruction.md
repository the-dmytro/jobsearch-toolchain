# Agent playbook: LinkedIn alert triage

Use this only after the user selects LinkedIn and configures a mail connector or supplies exported alerts. The workflow is profile-driven and has no default role, location, compensation, identity, or cadence.

Inputs are the filled files listed in the selected private profile, messages returned by the configured inbox, and user-approved storage, notification, and scheduling settings. Never use public templates as personal facts. Ask when work authorization, location, dealbreakers, or writing preferences are unknown.

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker fetch-mail-folder --provider linkedin --output outputs/automation-payloads/linkedin-mail.payload.json
.venv/bin/python -m jobtracker validate-payload --provider linkedin --payload outputs/automation-payloads/linkedin-mail.payload.json
.venv/bin/python -m jobtracker dedupe-candidates --provider linkedin --payload outputs/automation-payloads/linkedin-mail.payload.json --payload-dir outputs/automation-payloads --output outputs/automation-payloads/linkedin-mail.deduped.payload.json
.venv/bin/python -m jobtracker upsert-run --provider linkedin --payload outputs/automation-payloads/linkedin-mail.deduped.payload.json
```

Persist through the configured `JobStore`; SQLite is the default. JSON payload artifacts are retained for audit and PostgreSQL replay. Use deterministic output for source facts and the private profile for fit judgments. Separate evidence, inference, and unknowns.

Report message count, opportunities, duplicate handling, persisted run key, artifact paths, optional delivery results, and blockers.

# Automation

Automation is optional and is configured only after manual and local SQLite runs succeed. See [the automation onboarding chapter](onboarding/AUTOMATION.md) and the parameterized [agent playbooks](playbooks/).

Configured pipelines use named TOML tables:

```toml
[pipelines.jobboards]
type = "jobboard"
profile = "generic"
providers = ["example_jsonld"]
include_db = true
```

Run manually:

```bash
.venv/bin/python -m jobtracker run jobboards --dry-run
.venv/bin/python -m jobtracker run jobboards
```

Select cadence, time zone, retry rules, and delivery channels with the user. Do not copy a schedule into an active system until those choices and a live connector smoke test are confirmed.

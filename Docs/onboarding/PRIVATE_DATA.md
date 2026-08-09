# Private profile and configuration

Run `jobtracker init` once. It creates ignored `config/jobsearch.toml` and `profile/` files from neutral public templates.

Personal facts must come from the user or files the user explicitly supplies. Do not infer experience, identity, dates, location, authorization, compensation, preferences, or project outcomes. Keep unknowns visible.

Tracked public paths contain only schemas, generic templates, fixtures, examples, code, and documentation. Ignored private paths include `.env`, `config/jobsearch.toml`, `config/jobsearch.local.toml`, filled `profile/`, `outputs/`, local databases, reports, and `.jobsearch-onboarding.json`.

Before any public commit:

```bash
python3 scripts/scan_pii.py
git status --short --ignored
```

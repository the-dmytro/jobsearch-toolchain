# Agent-led kickstart protocol

This protocol turns a fresh clone into a private, working setup. Ask; do not infer. Write personal facts only to ignored `profile/`, non-secret choices only to ignored `config/jobsearch.toml`, and credentials only to ignored `.env`.

## 1. Establish the boundary

Explain that the standard setup uses Python, SQLite, and local artifacts. Ask whether the user wants optional mail, notifications, PostgreSQL or hosted Supabase, CRM, or scheduling. Do not introduce Docker; mention it only if the user explicitly selects the advanced local Supabase path.

Confirm the project root, operating system (macOS or Linux), Python version, and whether an existing CV/profile can be read from a user-provided local path. Never move or copy credentials without explicit instruction.

Before choosing storage, find out where you are: run `.venv/bin/python -m jobtracker probe-environment --format text` and follow [environment setup](ENVIRONMENT_SETUP.md). If the repository already has a config and profile from another environment, treat it as an existing project: keep its database and only set this environment's `JOBTRACKER_STORE_CONNECTOR`.

## 2. Prove the public fixture core

Run installation and deterministic fixture checks before collecting personal data:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m jobtracker benchmark-sources \
  --providers example_jsonld \
  --fixture-dir jobtracker/fixtures/provider_fetch
```

Report exact results. A failed fixture is a toolchain problem, not a user-profile problem.

## 3. Interview the user

Collect and confirm, in manageable groups:

- CV source and which facts may be retained locally;
- target roles, seniority constraints, industries, and opportunity types;
- location, work model, travel, time-zone, and work-authorization constraints;
- compensation or rate constraints and dealbreakers;
- writing tone, length, language, and terms to use or avoid;
- project evidence: problem, personal contribution, technology, and verifiable outcome;
- chosen search sources and any service-specific target identifiers;
- optional mail inbox, alert parsers, outbound mail, and report recipient;
- optional notifications and channels;
- SQLite (local only) or a shared PostgreSQL database, where it is hosted, and how this environment reaches it (see [environment setup](ENVIRONMENT_SETUP.md); never assume a provider);
- optional CRM;
- desired automation cadence, quiet periods, and failure notifications.

Summarize the answers and ask for correction before writing. Unknowns remain placeholders or explicit `unknown` notes.

## 4. Create ignored private files

```bash
.venv/bin/python -m jobtracker init
```

Fill `profile/cv.md`, `profile/preferences.md`, `profile/project_evidence.md`, `profile/writing_style.md`, `profile/provider_targets.toml`, and `profile/generic.toml`. Update ignored `config/jobsearch.toml`. Create `.env` only for selected connectors that need secrets.

Run `git status --ignored --short` and confirm private files are ignored. Never use `git add -f` for them.

## 5. Advance readiness in order

1. Core fixture demo.
2. Private profile complete.
3. Offline doctor ready.
4. Fixture pipeline persisted to local SQLite and replayed with the same run key.
5. Selected live sources.
6. Optional mail and notifications.
7. Optional PostgreSQL/Supabase and CRM.
8. Optional scheduling.

Commands for stages 3 and 4:

```bash
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m jobtracker run jobboards \
  --fixture-dir jobtracker/fixtures/provider_fetch
.venv/bin/python -m jobtracker run jobboards \
  --fixture-dir jobtracker/fixtures/provider_fetch
```

Verify both runs have the same provider run key and SQLite contains one logical run, not duplicate opportunity rows.

## 6. Connect selected services

For each selected connector, tell the user exactly which account setting, token, app password, folder, board identifier, or webhook is needed; where it is stored; the minimum required permission; and how to revoke it. Ask the user to set secrets in `.env` themselves when possible. Run `doctor` after each component, then a narrow dry run, then a live run.

## 7. Finish with evidence

Report completed stages, commands and tests passed, private paths created, connectors selected, live checks passed or unavailable, blockers, and the next safe action. Do not label optional or unavailable checks as passed.

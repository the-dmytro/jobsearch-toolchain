# Agent entrypoint

Start a new-user setup with [Docs/onboarding/AGENT_KICKSTART.md](Docs/onboarding/AGENT_KICKSTART.md). To set up a cloud environment (Claude Code on the web, Codex, …), follow [Docs/onboarding/CLOUD_ENVIRONMENT.md](Docs/onboarding/CLOUD_ENVIRONMENT.md). Use [Docs/README.md](Docs/README.md) for manual setup and subsystem guides.

Non-negotiable boundaries:

- Ask for personal facts; never invent them. Write them only to ignored `profile/` files.
- Keep credentials in ignored `.env`; never put secrets in TOML, output, logs, commits, or prompts.
- Resolve configured relative paths from the selected project root.
- Use only the store named in `[store]` of the config. Never add or use a fallback to another store or location; a failed write is an error.
- Validate automation payloads against `schemas/automation-payload.v1.schema.json`.
- Keep the Python and optional CRM layers independent.
- Before any public commit or PR, run the complete gates in `Docs/contributing/RELEASE_CHECKLIST.md`, including `python3 scripts/scan_pii.py`.

Reusable changes go to a public branch and PR. Personal overlays consume public releases and must never be pushed to the public remote.

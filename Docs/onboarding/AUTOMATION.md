# Notifications and automation

Notifications and scheduling are opt-in. First prove a manual dry run and a persisted local run. Then configure selected channels, run `doctor`, and test one delivery with non-sensitive fixture content.

Ask the user for cadence, time zone, quiet periods, overlap/retry behavior, and failure reporting. Do not embed a default schedule. Templates under `examples/automation/` are disabled until configured.

Agent playbooks in `Docs/playbooks/` read the selected profile/config and must not introduce role, location, salary, identity, or cadence assumptions.

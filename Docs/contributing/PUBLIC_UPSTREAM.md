# Public upstream and private overlays

`jobsearch-toolchain` is the canonical reusable source. Public branches and pull requests contain deterministic code, neutral fixtures/templates, tests, and documentation only.

A private `JobSearch` repository may consume signed public tags and retain ignored personal configuration outside public Git history. Configure the public repository as `upstream` and the private repository as `origin`. Never push the private overlay branch to the public remote.

From an existing private clone whose `origin` is already private, run
`scripts/setup_remotes.sh`. The script only adds or verifies `upstream`; it refuses a
conflicting URL and does not create branches, rewrite history, or push.

Reusable work originates publicly. If a private incident needs an emergency patch, record the upstream issue/PR reference and port only the generalized change. Inspect the exact diff and run `scripts/scan_pii.py` before any public push.

Release-history rewriting, branch deletion, force updates, ruleset changes, tag publication, and private-branch reconstruction are maintainer operations requiring explicit approval and the release checklist. They are not onboarding steps.

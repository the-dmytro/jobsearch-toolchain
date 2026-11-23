#!/usr/bin/env bash
# Verify a session before working: the config selects one store (and, for a shared
# database, one environment and connector), that connector's settings are present,
# and the store answers. Secret values are never printed.
# Usage: scripts/cloud/verify.sh [project-root]
set -uo pipefail
root="${1:-.}"
python="$root/.venv/bin/python"
[ -x "$python" ] || python="python3"

if [ ! -f "$root/config/jobsearch.toml" ]; then
  echo "missing config/jobsearch.toml: see Docs/onboarding/ENVIRONMENT_SETUP.md"
  exit 1
fi
"$python" -m jobtracker probe-environment --root "$root" --timeout 5 --format text
"$python" -m jobtracker doctor --root "$root"

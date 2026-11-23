#!/usr/bin/env bash
# Environment setup script for the JobSearch toolchain (any platform with bash and python3).
# Use it as the environment's setup or provisioning script, or run it by hand.
# Run it from a checkout or from the directory that holds checkouts. It reads no
# secrets, is idempotent, and skips directories that are not a toolchain checkout.
set -euo pipefail

install_checkout() {
  local dir="$1"
  grep -q 'name = "jobsearch-tracker"' "$dir/pyproject.toml" 2>/dev/null || return 0
  echo "jobsearch setup: $dir"
  python3 -m venv "$dir/.venv"
  "$dir/.venv/bin/pip" install --quiet --upgrade pip
  "$dir/.venv/bin/pip" install --quiet -e "$dir[postgres]"
}

install_checkout "."
for dir in */; do
  install_checkout "${dir%/}"
done

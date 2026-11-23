#!/usr/bin/env bash
# Cloud environment setup script for the JobSearch toolchain.
# Paste this file's body into the environment's setup script. It runs as root
# before the agent starts, from the directory that holds the repository checkouts
# (or from inside a checkout). Environment variables are not available here.
# It is idempotent and skips directories that are not a toolchain checkout.
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

#!/usr/bin/env bash
# Add the canonical public repository to an existing private-overlay clone.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PUBLIC_URL="${JOBSEARCH_PUBLIC_REMOTE:-https://github.com/the-dmytro/jobsearch-toolchain.git}"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "error: origin must already point to the private overlay repository" >&2
  exit 2
fi

if git remote get-url upstream >/dev/null 2>&1; then
  CURRENT_UPSTREAM="$(git remote get-url upstream)"
  if [[ "$CURRENT_UPSTREAM" != "$PUBLIC_URL" ]]; then
    echo "error: upstream already points to $CURRENT_UPSTREAM" >&2
    echo "expected: $PUBLIC_URL" >&2
    exit 2
  fi
else
  git remote add upstream "$PUBLIC_URL"
fi

echo "Remote topology ready:"
echo "  origin   -> $(git remote get-url origin) (private overlay)"
echo "  upstream -> $(git remote get-url upstream) (public toolchain)"
echo "No branch, tag, or history was changed."

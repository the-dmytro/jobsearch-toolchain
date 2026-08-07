#!/usr/bin/env bash
# Configure dual-remote topology for personal vs public development.
# Run once after cloning.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Rename existing origin to private if not already done
if git remote get-url origin &>/dev/null; then
  if ! git remote get-url private &>/dev/null; then
    git remote rename origin private
    echo "Renamed origin -> private ($(git remote get-url private))"
  fi
fi

# Add public remote (update URL when repo is created)
PUBLIC_URL="${JOBSEARCH_PUBLIC_REMOTE:-https://github.com/the-dmytro/jobsearch-toolchain.git}"
if ! git remote get-url origin &>/dev/null; then
  git remote add origin "$PUBLIC_URL"
  echo "Added origin -> $PUBLIC_URL"
fi

# Create personal branch from current main if missing
if ! git show-ref --verify --quiet refs/heads/personal; then
  git branch personal
  echo "Created branch: personal"
fi

echo ""
echo "Topology:"
echo "  origin  -> public repo (main branch)"
echo "  private -> personal repo (personal branch)"
echo ""
echo "Day-to-day:"
echo "  git checkout personal          # primary worktree"
echo "  git merge main                 # pull public updates"
echo "  git worktree add ../JobSearch-public main  # public-only work"

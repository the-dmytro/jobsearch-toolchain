#!/usr/bin/env bash
# Verify a session before working: required variables are present (values are
# never printed), the config names one store, and that store answers.
# Usage: scripts/cloud/verify.sh [project-root]
set -uo pipefail
root="${1:-.}"
python="$root/.venv/bin/python"
[ -x "$python" ] || python="python3"
status=0

need() {
  if [ -n "${!1:-}" ]; then echo "ok      $1 is set"; else echo "missing $1"; status=1; fi
}

if [ ! -f "$root/config/jobsearch.toml" ]; then
  echo "missing config/jobsearch.toml (run: $python -m jobtracker init --template cloud)"
  exit 1
fi
backend="$("$python" -c 'import sys,tomllib;c=tomllib.load(open(sys.argv[1],"rb")).get("store",{});print(c.get("backend",""),c.get("transport",""))' "$root/config/jobsearch.toml")"
echo "store   $backend"
case "$backend" in
  "postgres supabase_https"|"supabase supabase_https") need SUPABASE_URL; need SUPABASE_SECRET_KEY ;;
  "postgres direct"|"postgresql direct"|"supabase direct") need JOBTRACKER_DATABASE_URL ;;
  "sqlite "*) echo "note    sqlite keeps data on this machine only; it is not shared with other environments" ;;
  *) echo "invalid store.backend/transport in config/jobsearch.toml"; status=1 ;;
esac
[ -f "$root/profile/provider_targets.toml" ] || { echo "missing profile/provider_targets.toml"; status=1; }

"$python" -m jobtracker doctor --root "$root" || status=1
exit "$status"

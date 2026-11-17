#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
UNSUPPORTED = {
    "fetch-myboard": "nonexistent provider-specific command",
    "register_parser": "nonexistent mail registration API",
    'kind = "eml"': "EML is not an inbox connector kind",
    "def upsert_run(": "obsolete JobStore signature",
    "[[pipelines]]": "obsolete pipeline array syntax",
    "[identity]": "unsupported config section",
    "Supabase-backed": "obsolete product description",
}
JOBTRACKER_COMMANDS = {
    "benchmark-sources",
    "build-local-index",
    "calendar",
    "check-duplicates",
    "db-smoke",
    "dedupe-candidates",
    "doctor",
    "discover-mail-folders",
    "export-summary",
    "fetch-mail-folder",
    "fetch-dou",
    "fetch-workua",
    "fetch-djinni",
    "fetch-greenhouse-jobs",
    "fetch-source",
    "import-greenhouse",
    "import-legacy",
    "import-linkedin-tracking",
    "init",
    "migrate",
    "parse-upwork-alerts",
    "prepare-jobboard-run",
    "run",
    "send-report-email",
    "sync-pending-runs",
    "upsert-run",
    "validate-payload",
}


def tracked_markdown(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = [root / value for value in result.stdout.decode().split("\0") if value]
    return [path for path in paths if path.exists()]


def _local_link_target(path: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>").split("#", 1)[0]
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    return (path.parent / target).resolve()


def check_document(path: Path, *, root: Path, allowed_placeholders: set[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    label = path.relative_to(root).as_posix()
    issues: list[str] = []
    for target in LINK_RE.findall(text):
        local = _local_link_target(path, target)
        if local is not None and not local.exists():
            issues.append(f"{label}: broken local link {target!r}")
    for token, reason in UNSUPPORTED.items():
        if token in text:
            issues.append(f"{label}: {reason}: {token!r}")
    for placeholder in PLACEHOLDER_RE.findall(text):
        if placeholder not in allowed_placeholders:
            issues.append(f"{label}: undocumented placeholder {placeholder}")
    for line_number, line in enumerate(text.splitlines(), 1):
        if " -m jobtracker " not in line:
            continue
        tail = line.split(" -m jobtracker ", 1)[1].strip()
        command = tail.split(maxsplit=1)[0] if tail else ""
        if command and not command.startswith(("<", "`")) and command not in JOBTRACKER_COMMANDS:
            issues.append(f"{label}:{line_number}: unsupported jobtracker command {command!r}")
    return issues


def collect_issues(root: Path) -> list[str]:
    templates = root / "profile/templates/generic"
    allowed = {"{{REPORT_EMAIL}}", "{{PLACEHOLDER}}"}
    for path in templates.glob("*"):
        if path.is_file():
            allowed.update(PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8")))
    issues: list[str] = []
    for path in tracked_markdown(root):
        issues.extend(check_document(path, root=root, allowed_placeholders=allowed))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate tracked documentation")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    issues = collect_issues(args.root)
    if issues:
        print("Documentation check FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("Documentation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

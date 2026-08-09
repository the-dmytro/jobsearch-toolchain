#!/usr/bin/env python3
"""Scan tracked files and staged diffs for PII deny-list matches."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_DENYLIST = Path(".pii-denylist.txt")
SCAN_SKIP_PATHS = frozenset(
    {
        DEFAULT_DENYLIST,
        Path("scripts/scan_pii.py"),
        Path("tests/test_public_safety.py"),
    }
)
FALLBACK_PATTERNS = [
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
]

ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "linkedin.com",
    "upwork.com",
    "greenhouse.io",
    "greenhouse-mail.io",
    "jobgether.com",
    "lever.co",
}
EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+)@([A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\w)(?:(?:\+\d{1,3}[ .-]?(?:\(\d{2,4}\)|\d{2,4}))|(?:\(\d{2,4}\))|(?:\d{3}))[ .-]\d{3}[ .-]\d{4}(?!\w)"
)
HOME_PATH_RE = re.compile(r"(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)")
CONFLICT_RE = re.compile(r"^(?:<{7}(?: .*)?|={7}|>{7}(?: .*)?)$", re.MULTILINE)
SECRET_RES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


def load_patterns(path: Path) -> list[str]:
    if path.exists():
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return lines or FALLBACK_PATTERNS
    return FALLBACK_PATTERNS


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        check=True,
    )
    paths = [Path(p) for p in result.stdout.decode().split("\0") if p]
    return [path for path in paths if path not in SCAN_SKIP_PATHS]


def scan_tracked_path(path: Path) -> list[str]:
    """Reject files that belong to an ignored private runtime tree."""
    value = path.as_posix()
    if value == "config/jobsearch.toml":
        return [f"{value}: generated user config must not be tracked"]
    if value.startswith("profile/") and not value.startswith("profile/templates/"):
        return [f"{value}: filled profile data must not be tracked"]
    if value.startswith(("outputs/", "Docs/Tracking/")):
        return [f"{value}: generated/private output must not be tracked"]
    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return [f"{value}: local database must not be tracked"]
    return []


def staged_diff_text() -> str:
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="replace")


def staged_added_text() -> str:
    """Return only added lines from the staged diff (ignore removals and excluded paths)."""
    excluded = {path.as_posix() for path in SCAN_SKIP_PATHS}
    current_file: str | None = None
    added: list[str] = []
    for line in staged_diff_text().splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if current_file in excluded:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added)


def scan_text(text: str, patterns: list[str], label: str) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if pattern in text:
            hits.append(f"{label}: matched deny-list pattern: {pattern!r}")
    return hits


def scan_structural_text(text: str, label: str) -> list[str]:
    hits: list[str] = []
    if CONFLICT_RE.search(text):
        hits.append(f"{label}: contains a merge conflict marker")
    if HOME_PATH_RE.search(text):
        hits.append(f"{label}: contains an absolute user home path")
    for match in EMAIL_RE.finditer(text):
        domain = match.group(2).lower()
        if (
            domain not in ALLOWED_EMAIL_DOMAINS
            and not any(domain.endswith(f".{allowed}") for allowed in ALLOWED_EMAIL_DOMAINS)
            and not domain.endswith((".example", ".test", ".invalid"))
        ):
            hits.append(f"{label}: contains an email address: {match.group(0)!r}")
    if PHONE_RE.search(text):
        hits.append(f"{label}: contains a phone number")
    for secret_re in SECRET_RES:
        if secret_re.search(text):
            hits.append(f"{label}: contains secret-like material")
    return hits


def scan_file(path: Path, patterns: list[str]) -> list[str]:
    if not path.exists() or path.is_dir():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(content, patterns, str(path)) + scan_structural_text(content, str(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan for PII deny-list matches")
    parser.add_argument(
        "--denylist",
        type=Path,
        default=DEFAULT_DENYLIST,
        help="Path to deny-list file (one pattern per line)",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        help="Only scan staged diff",
    )
    args = parser.parse_args(argv)

    patterns = load_patterns(args.denylist)
    violations: list[str] = []

    if args.staged_only:
        staged = staged_added_text()
        violations.extend(scan_text(staged, patterns, "staged diff"))
        violations.extend(scan_structural_text(staged, "staged diff"))
    else:
        for path in tracked_files():
            violations.extend(scan_tracked_path(path))
            violations.extend(scan_file(path, patterns))
        staged = staged_added_text()
        violations.extend(scan_text(staged, patterns, "staged diff"))
        violations.extend(scan_structural_text(staged, "staged diff"))

    if violations:
        print("PII scan FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("PII scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Scan tracked files and staged diffs for PII deny-list matches."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_DENYLIST = Path(".pii-denylist.txt")
SCAN_SKIP_PATHS = frozenset(
    {
        DEFAULT_DENYLIST,
        Path("scripts/scan_pii.py"),
    }
)
FALLBACK_PATTERNS = [
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
    "[REDACTED]",
]


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
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    paths = [Path(p) for p in result.stdout.decode().split("\0") if p]
    return [path for path in paths if path not in SCAN_SKIP_PATHS]


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


def scan_file(path: Path, patterns: list[str]) -> list[str]:
    if not path.exists() or path.is_dir():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(content, patterns, str(path))


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
        violations.extend(scan_text(staged_added_text(), patterns, "staged diff"))
    else:
        for path in tracked_files():
            violations.extend(scan_file(path, patterns))
        violations.extend(scan_text(staged_added_text(), patterns, "staged diff"))

    if violations:
        print("PII scan FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("PII scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

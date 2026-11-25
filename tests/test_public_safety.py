from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("scan_pii", ROOT / "scripts" / "scan_pii.py")
assert SPEC and SPEC.loader
scan_pii = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_pii)


class PublicSafetyTests(unittest.TestCase):
    def test_detects_merge_conflict_markers(self) -> None:
        hits = scan_pii.scan_structural_text(
            "<<<<<<< HEAD\nvalue\n=======\nother\n>>>>>>> branch", "README.md"
        )

        self.assertTrue(any("conflict marker" in hit for hit in hits))

    def test_detects_home_paths_email_and_phone(self) -> None:
        text = "Contact person@personal-mail.dev at +1 (415) 555-0199 in /Users/person/private"

        hits = scan_pii.scan_structural_text(text, "notes.md")

        self.assertTrue(any("home path" in hit for hit in hits))
        self.assertTrue(any("email address" in hit for hit in hits))
        self.assertTrue(any("phone number" in hit for hit in hits))

    def test_reserved_example_values_are_allowed(self) -> None:
        text = "Use person@example.com and https://careers.example.invalid/jobs in documentation."

        self.assertEqual(scan_pii.scan_structural_text(text, "examples/README.md"), [])

    def test_private_tracked_paths_are_rejected(self) -> None:
        self.assertTrue(scan_pii.scan_tracked_path(Path("profile/cv.md")))
        self.assertTrue(scan_pii.scan_tracked_path(Path("config/jobsearch.toml")))
        self.assertFalse(scan_pii.scan_tracked_path(Path("profile/templates/generic/cv.md")))


if __name__ == "__main__":
    unittest.main()


class DenylistSourceTests(unittest.TestCase):
    def test_denylist_file_is_preferred_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "denylist.txt"
            path.write_text("# comment\nalpha-token\n\n", encoding="utf-8")

            patterns = scan_pii.load_patterns(path, {"PII_DENYLIST": "from-env"})

        self.assertEqual(patterns, ["alpha-token"])

    def test_environment_denylist_is_used_when_file_is_missing(self) -> None:
        missing = Path("does-not-exist-denylist.txt")

        patterns = scan_pii.load_patterns(missing, {"PII_DENYLIST": "first\n\nsecond\n"})

        self.assertEqual(patterns, ["first", "second"])

    def test_no_denylist_source_returns_none(self) -> None:
        missing = Path("does-not-exist-denylist.txt")

        self.assertIsNone(scan_pii.load_patterns(missing, {}))
        self.assertIsNone(scan_pii.load_patterns(missing, {"PII_DENYLIST": "   "}))

    def test_generic_mode_runs_only_secret_and_conflict_checks(self) -> None:
        text = "<<<<<<< HEAD\nkey -----BEGIN PRIVATE KEY----- person@personal-mail.dev /Users/person\n"

        hits = scan_pii.scan_content(text, "notes.md", None)

        self.assertTrue(any("conflict marker" in hit for hit in hits))
        self.assertTrue(any("secret-like material" in hit for hit in hits))
        self.assertFalse(any("email address" in hit for hit in hits))
        self.assertFalse(any("home path" in hit for hit in hits))

    def test_configured_denylist_matches_literal_patterns(self) -> None:
        hits = scan_pii.scan_content("contains alpha-token here", "notes.md", ["alpha-token"])

        self.assertTrue(any("deny-list pattern" in hit for hit in hits))

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

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

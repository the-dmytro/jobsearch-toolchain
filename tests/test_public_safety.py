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

MISSING = Path("does-not-exist-denylist.txt")


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


class DenylistSourceTests(unittest.TestCase):
    def test_denylist_file_is_preferred_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "denylist.txt"
            path.write_text("# comment\nalpha-token\n\n", encoding="utf-8")

            patterns = scan_pii.load_patterns(path, {"PII_DENYLIST": "from-env"})

        self.assertEqual(patterns, ["alpha-token"])

    def test_environment_denylist_is_used_when_file_is_missing(self) -> None:
        patterns = scan_pii.load_patterns(MISSING, {"PII_DENYLIST": "first\n\nsecond\n"})

        self.assertEqual(patterns, ["first", "second"])

    def test_no_denylist_source_returns_none(self) -> None:
        self.assertIsNone(scan_pii.load_patterns(MISSING, {}))

    def test_blank_environment_denylist_counts_as_not_configured(self) -> None:
        self.assertIsNone(scan_pii.load_patterns(MISSING, {"PII_DENYLIST": "   \n\n"}))

    def test_comment_only_file_counts_as_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "denylist.txt"
            path.write_text("# only a comment\n\n# another\n", encoding="utf-8")

            self.assertIsNone(scan_pii.load_patterns(path, {}))
            self.assertEqual(scan_pii.load_patterns(path, {"PII_DENYLIST": "from-env"}), ["from-env"])

    def test_comment_only_environment_counts_as_not_configured(self) -> None:
        self.assertIsNone(scan_pii.load_patterns(MISSING, {"PII_DENYLIST": "# note\n"}))


class ScanContentTests(unittest.TestCase):
    def test_structural_checks_run_without_a_denylist(self) -> None:
        text = "Contact person@personal-mail.dev at +1 (415) 555-0199 in /Users/person/private"

        hits = scan_pii.scan_content(text, "notes.md", None)

        self.assertTrue(any("home path" in hit for hit in hits))
        self.assertTrue(any("email address" in hit for hit in hits))
        self.assertTrue(any("phone number" in hit for hit in hits))

    def test_generic_mode_flags_conflict_markers_and_secrets(self) -> None:
        text = "<<<<<<< HEAD\nkey -----BEGIN PRIVATE KEY-----\n"

        hits = scan_pii.scan_content(text, "notes.md", None)

        self.assertTrue(any("conflict marker" in hit for hit in hits))
        self.assertTrue(any("secret-like material" in hit for hit in hits))

    def test_reserved_example_values_pass_without_a_denylist(self) -> None:
        text = "Use person@example.com and https://careers.example.invalid/jobs in documentation."

        self.assertEqual(scan_pii.scan_content(text, "examples/README.md", None), [])

    def test_configured_denylist_matches_literal_patterns(self) -> None:
        hits = scan_pii.scan_content("contains alpha-token here", "notes.md", ["alpha-token"])

        self.assertTrue(any("deny-list pattern" in hit for hit in hits))

    def test_configured_denylist_keeps_structural_checks(self) -> None:
        hits = scan_pii.scan_content("reach person@personal-mail.dev", "notes.md", ["unrelated"])

        self.assertTrue(any("email address" in hit for hit in hits))
        self.assertFalse(any("deny-list pattern" in hit for hit in hits))


class SecretPatternTests(unittest.TestCase):
    def assertSecret(self, text: str) -> None:
        hits = scan_pii.scan_structural_text(text, "doc.md")
        self.assertTrue(
            any("secret-like material" in hit for hit in hits), f"expected a secret hit for {text!r}"
        )

    def assertNoSecret(self, text: str) -> None:
        hits = scan_pii.scan_structural_text(text, "doc.md")
        self.assertFalse(
            any("secret-like material" in hit for hit in hits), f"unexpected secret hit for {text!r}"
        )

    def test_supabase_jwt_is_detected(self) -> None:
        header = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        payload = "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UifQ"
        self.assertSecret(f"token={header}.{payload}.c2lnbmF0dXJlMTIzNDU")

    def test_placeholder_jwt_text_is_not_a_secret(self) -> None:
        self.assertNoSecret("Set the anon key, for example eyJ... or eyJhbGciOi.")

    def test_secret_key_prefix_is_detected(self) -> None:
        self.assertSecret("sb_secret_" + "A" * 24)

    def test_short_sb_secret_prefix_is_not_detected(self) -> None:
        self.assertNoSecret("sb_secret_short")

    def test_openai_and_anthropic_style_keys_are_detected(self) -> None:
        self.assertSecret("sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2")
        self.assertSecret("sk-ant-api03-" + "x" * 30)

    def test_kebab_case_words_are_not_sk_keys(self) -> None:
        self.assertNoSecret("task-management-system-overview-document")

    def test_slack_token_is_detected(self) -> None:
        self.assertSecret("xoxb-" + "1234567890-abcdefghij")

    def test_live_stripe_keys_are_detected(self) -> None:
        self.assertSecret("sk_live_" + "a" * 16)
        self.assertSecret("rk_live_" + "b" * 16)

    def test_test_mode_stripe_keys_are_not_detected(self) -> None:
        self.assertNoSecret("sk_test_" + "a" * 16)


if __name__ == "__main__":
    unittest.main()

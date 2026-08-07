"""Tests for the automation entry points: scaffolding, doctor, and pipeline runs."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from jobtracker import automation
from jobtracker.app_config.loader import AppConfig, load_app_config
from jobtracker.app_config.schema import ConfigValidationError
from jobtracker.automation import (
    check_db_connectivity,
    check_imap_connectivity,
    check_notifier_health,
    check_smtp_connectivity,
    run_doctor,
    run_pipeline,
    scaffold_config,
    validate_config,
)
from jobtracker.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "jobtracker" / "fixtures" / "provider_fetch"
TEMPLATE_DIR = REPO_ROOT / "profile" / "templates"
NOW = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)

# `profile/` is gitignored, so a fresh clone has no templates to seed a root from.
requires_profile_templates = unittest.skipUnless(
    TEMPLATE_DIR.exists(), "profile/templates is absent from this checkout"
)

IOS_PROFILE_FILES = [
    "profile/00_INSTRUCTIONS.md",
    "profile/01_PREFERENCES.md",
    "profile/04_LINKS_AND_CONTACTS.md",
    "profile/05_ROLE_TARGETS.md",
    "profile/CV_SOURCE.md",
]


def settings(**overrides) -> Settings:
    base = {
        "db_url": None,
        "test_db_url": None,
        "supabase_url": None,
        "secret_key": None,
        "service_role_key": None,
        "storage_bucket": "job-artifacts",
        "store_backend": "postgres",
        "artifact_backend": "local",
        "mail_folder_aliases": {},
        "own_report_senders": frozenset(),
        "s3_artifact_bucket": None,
        "s3_artifact_prefix": None,
    }
    base.update(overrides)
    return Settings(**base)


@requires_profile_templates
class ScaffoldedRootTestCase(unittest.TestCase):
    """Builds a throwaway project root seeded from the repository templates."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        (self.root / "config").mkdir()
        shutil.copyfile(
            REPO_ROOT / "config" / "jobsearch.example.toml",
            self.root / "config" / "jobsearch.example.toml",
        )
        shutil.copytree(REPO_ROOT / "profile" / "templates", self.root / "profile" / "templates")

    def scaffold(self, **kwargs) -> dict:
        return scaffold_config(root=self.root, **kwargs)

    def write_profile_documents(self) -> None:
        for relative_path in IOS_PROFILE_FILES:
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Resolved profile content with no unfilled tokens.\n", encoding="utf-8")

    def chdir_to_root(self) -> None:
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.root)


class ScaffoldConfigTests(ScaffoldedRootTestCase):
    def test_copies_the_example_config_and_profile_templates(self) -> None:
        result = self.scaffold()

        self.assertIn(str(self.root / "config" / "jobsearch.toml"), result["created"])
        self.assertIn(str(self.root / "profile" / "ios.toml"), result["created"])
        self.assertTrue((self.root / "profile" / "provider_targets.toml").exists())
        self.assertEqual(result["skipped"], [])

    def test_existing_files_are_skipped_unless_forced(self) -> None:
        self.scaffold()
        (self.root / "config" / "jobsearch.toml").write_text("# hand edited\n", encoding="utf-8")

        skipped = self.scaffold()

        self.assertIn(str(self.root / "config" / "jobsearch.toml"), skipped["skipped"])
        self.assertEqual(skipped["created"], [])
        self.assertEqual((self.root / "config" / "jobsearch.toml").read_text(encoding="utf-8"), "# hand edited\n")

        forced = self.scaffold(force=True)

        self.assertIn(str(self.root / "config" / "jobsearch.toml"), forced["created"])
        self.assertIn("[pipelines.jobboards]", (self.root / "config" / "jobsearch.toml").read_text(encoding="utf-8"))

    def test_missing_example_config_is_reported(self) -> None:
        (self.root / "config" / "jobsearch.example.toml").unlink()

        with self.assertRaises(FileNotFoundError):
            self.scaffold()


class ValidateConfigTests(unittest.TestCase):
    def build_config(self, **overrides) -> AppConfig:
        fields = {
            "root": REPO_ROOT,
            "paths": {
                "config_dir": "config",
                "profile_dir": "profile",
                "output_dir": "outputs/automation-payloads",
                "payload_dir": "outputs/automation-payloads",
            },
            "pipelines": {
                "jobboards": {
                    "type": "jobboard",
                    "profile": "ios",
                    "providers": ["dou"],
                    "output_dir": "outputs/automation-payloads",
                    "payload_dir": "outputs/automation-payloads",
                    "include_db": True,
                    "max_pages": 1,
                    "detail_limit": None,
                    "notify_channels": ["email"],
                }
            },
            "notify": {"email": {"to": "me@example.com"}},
            "sources": [],
        }
        fields.update(overrides)
        return AppConfig(**fields)

    def test_missing_profile_is_reported(self) -> None:
        config = self.build_config(paths={**self.build_config().paths, "profile_dir": "no-such-profile-dir"})

        issues = validate_config(config)

        self.assertTrue(any("pipeline jobboards" in issue for issue in issues))

    def test_unconfigured_notify_channel_is_reported(self) -> None:
        config = self.build_config(notify={})

        issues = validate_config(config)

        self.assertTrue(any("notify channel 'email' is not configured" in issue for issue in issues))

    @requires_profile_templates
    def test_no_issues_when_profile_and_channels_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "profile").mkdir()
            shutil.copyfile(REPO_ROOT / "profile" / "templates" / "ios.toml", root / "profile" / "ios.toml")
            config = self.build_config(root=root)

            self.assertEqual(validate_config(config), [])


class RunDoctorTests(ScaffoldedRootTestCase):
    def test_missing_config_short_circuits_with_an_issue(self) -> None:
        report = run_doctor(root=self.root, skip_network=True)

        self.assertFalse(report["ok"])
        self.assertEqual(report["checks"], {})
        self.assertTrue(any("Config file not found" in issue for issue in report["issues"]))

    def test_unfilled_profile_documents_are_reported(self) -> None:
        self.scaffold()

        report = run_doctor(root=self.root, skip_network=True)

        self.assertFalse(report["ok"])
        self.assertIn("schema", report["checks"])
        self.assertIn("profile_placeholders", report["checks"])
        self.assertEqual(report["checks"]["schema"], [])
        placeholder_issues = {issue["issue"] for issue in report["checks"]["profile_placeholders"]}
        self.assertTrue(placeholder_issues)
        self.assertTrue(
            any("unresolved placeholders" in issue for issue in placeholder_issues),
            placeholder_issues,
        )
        self.assertNotIn("database", report["checks"])

    def test_unresolved_placeholders_are_reported(self) -> None:
        self.scaffold()
        self.write_profile_documents()
        (self.root / "profile" / "CV_SOURCE.md").write_text("Contact: {{REPORT_EMAIL}}\n", encoding="utf-8")

        report = run_doctor(root=self.root, skip_network=True)

        self.assertFalse(report["ok"])
        self.assertTrue(any("{{REPORT_EMAIL}}" in issue for issue in report["issues"]))

    def test_a_fully_filled_project_passes_the_offline_checks(self) -> None:
        self.scaffold()
        self.write_profile_documents()

        report = run_doctor(root=self.root, skip_network=True)

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["checks"]["schema"], [])
        self.assertEqual(report["checks"]["profile_placeholders"], [])

    def test_explicit_config_path_is_honoured(self) -> None:
        self.scaffold()
        self.write_profile_documents()

        report = run_doctor(
            config_path=self.root / "config" / "jobsearch.toml",
            root=self.root,
            skip_network=True,
        )

        self.assertTrue(report["ok"], report["issues"])


class ConnectivityCheckTests(unittest.TestCase):
    def test_database_check_reports_an_unconfigured_url(self) -> None:
        with mock.patch.object(automation, "load_settings", return_value=settings()):
            self.assertEqual(
                check_db_connectivity(),
                ["database: JOBTRACKER_DATABASE_URL is not configured"],
            )

    def test_database_check_wraps_connection_errors(self) -> None:
        with mock.patch.object(automation, "load_settings", return_value=settings(db_url="postgres://x")):
            with mock.patch.object(automation, "connect", side_effect=RuntimeError("connection refused")):
                issues = check_db_connectivity()

        self.assertEqual(issues, ["database: connection refused"])

    def test_imap_check_wraps_client_errors(self) -> None:
        with mock.patch.object(automation, "MailImapClient", side_effect=RuntimeError("no credentials")):
            self.assertEqual(check_imap_connectivity(), ["imap: no credentials"])

    def test_imap_check_flags_an_empty_folder_list(self) -> None:
        client = mock.MagicMock()
        client.__enter__.return_value.list_folders.return_value = []

        with mock.patch.object(automation, "MailImapClient", return_value=client):
            self.assertEqual(check_imap_connectivity(), ["imap: connected but no folders returned"])

    def test_smtp_check_wraps_construction_errors(self) -> None:
        with mock.patch.object(automation, "SmtpMailSender", side_effect=RuntimeError("missing password")):
            self.assertEqual(check_smtp_connectivity(), ["smtp: missing password"])

    def test_notifier_health_is_reported_per_channel(self) -> None:
        config = AppConfig(
            root=REPO_ROOT,
            paths={
                "config_dir": "config",
                "profile_dir": "profile",
                "output_dir": "outputs",
                "payload_dir": "outputs",
            },
            pipelines={},
            notify={"email": {"to": ""}, "webhook": {"url": "https://hooks.example.com/1"}},
            sources=[],
        )

        results = check_notifier_health(config)

        self.assertEqual(set(results), {"email", "webhook"})
        self.assertTrue(results["email"])
        self.assertEqual(results["webhook"], [])


class RunPipelineTests(ScaffoldedRootTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.scaffold()
        self.write_profile_documents()

    def test_dry_run_prepares_payloads_without_storing_or_notifying(self) -> None:
        self.chdir_to_root()

        result = run_pipeline(
            "jobboards",
            root=self.root,
            fixture_dir=FIXTURE_DIR,
            now=NOW,
            dry_run=True,
        )

        self.assertEqual(result["pipeline"], "jobboards")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["stored"], [])
        self.assertEqual(result["notifications"], [])

        manifest = result["manifest"]
        self.assertEqual(manifest["profile"]["slug"], "ios")
        self.assertEqual(manifest["providers"], ["dou", "workua", "djinni"])
        self.assertEqual(manifest["run"]["run_key"], "ua-jobboards-2026-04-29")
        self.assertEqual(manifest["run"]["status"], "completed")
        self.assertEqual(manifest["db"]["status"], "skipped")
        self.assertTrue(Path(manifest["manifest_path"]).exists())
        self.assertEqual(len(manifest["provider_runs"]), 3)
        for provider_run in manifest["provider_runs"]:
            with self.subTest(provider=provider_run["provider"]):
                self.assertGreaterEqual(provider_run["opportunities"], 1)
                self.assertTrue(Path(provider_run["deduped_payload_path"]).exists())

    def test_dry_run_payloads_are_valid_json_documents(self) -> None:
        self.chdir_to_root()

        manifest = run_pipeline(
            "jobboards", root=self.root, fixture_dir=FIXTURE_DIR, now=NOW, dry_run=True
        )["manifest"]

        payload = json.loads(Path(manifest["provider_runs"][0]["payload_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["metadata"]["jobboard_profile"]["slug"], "ios")
        self.assertIn("opportunities", payload)

    def test_unknown_pipeline_names_are_rejected(self) -> None:
        self.chdir_to_root()

        with self.assertRaises(ValueError) as caught:
            run_pipeline("nope", root=self.root, dry_run=True)

        self.assertIn("Unknown pipeline", str(caught.exception))

    def test_missing_config_raises_a_validation_error(self) -> None:
        (self.root / "config" / "jobsearch.toml").unlink()

        with self.assertRaises(ConfigValidationError):
            run_pipeline("jobboards", root=self.root, dry_run=True)

    def test_pipeline_config_is_read_from_the_scaffolded_root(self) -> None:
        config = load_app_config(root=self.root)

        self.assertEqual(config.pipelines["jobboards"]["notify_channels"], ["email"])
        self.assertEqual(config.pipelines["jobboards"]["type"], "jobboard")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobtracker.app_config.loader import load_app_config
from jobtracker.app_config.profiles import load_profile
from jobtracker.app_config.schema import (
    ConfigValidationError,
    find_placeholders,
    scan_profile_placeholders,
    validate_profile_config,
)
from jobtracker.app_config.loader import AppConfig
from jobtracker.automation import scaffold_config, validate_config


class ConfigTests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_validate_jobsearch_example_config(self) -> None:
        config = load_app_config(self.repo_root / "config/jobsearch.example.toml", root=self.repo_root)
        self.assertIn("jobboards", config.pipelines)
        self.assertEqual(config.pipelines["jobboards"]["profile"], "ios")

    def test_load_ios_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_dir = Path(temp_dir)
            template = self.repo_root / "profile/templates/ios.toml"
            (profile_dir / "ios.toml").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            profile = load_profile("ios", profile_dir=profile_dir)
            self.assertEqual(profile.slug, "ios")
            self.assertTrue(profile.targets_path.exists() or (self.repo_root / "jobtracker/fixtures/provider_targets.toml").exists())

    def test_scaffold_config_copies_markdown_templates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            example = self.repo_root / "config/jobsearch.example.toml"
            (root / "config/jobsearch.example.toml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            templates = root / "profile/templates"
            templates.mkdir(parents=True)
            (templates / "ios.toml").write_text("slug = 'ios'\n", encoding="utf-8")
            # minimal valid ios is not needed for copy test — copy raw files
            (templates / "ios.toml").write_text(
                (self.repo_root / "profile/templates/ios.toml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (templates / "00_INSTRUCTIONS.md").write_text("# {{OWNER_NAME}}\n", encoding="utf-8")
            (templates / "project-bank.example.md").write_text("# bank\n", encoding="utf-8")
            result = scaffold_config(root=root)
            self.assertTrue((root / "profile/00_INSTRUCTIONS.md").exists())
            self.assertTrue((root / "profile/project-banks/example.md").exists())
            self.assertTrue(any(path.endswith("00_INSTRUCTIONS.md") for path in result["created"]))

    def test_validate_config_reports_missing_notify_channel(self) -> None:
        config = AppConfig(
            root=self.repo_root,
            paths={"config_dir": "config", "profile_dir": "profile", "output_dir": "outputs/automation-payloads", "payload_dir": "outputs/automation-payloads"},
            pipelines={
                "jobboards": {
                    "type": "jobboard",
                    "profile": "ios",
                    "providers": ["dou"],
                    "output_dir": "outputs/automation-payloads",
                    "payload_dir": "outputs/automation-payloads",
                    "include_db": True,
                    "max_pages": 1,
                    "detail_limit": None,
                    "notify_channels": ["missing"],
                }
            },
            notify={},
            sources=[],
        )
        issues = validate_config(config)
        self.assertTrue(any("missing" in issue for issue in issues))

    def test_find_placeholders(self) -> None:
        self.assertEqual(find_placeholders("hello {{REPORT_EMAIL}}"), ["{{REPORT_EMAIL}}"])

    def test_scan_profile_placeholders_detects_unresolved_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_file = root / "profile.md"
            profile_file.write_text("Contact: {{REPORT_EMAIL}}", encoding="utf-8")
            issues = scan_profile_placeholders([str(profile_file)], root=root)
            self.assertEqual(len(issues), 1)
            self.assertIn("{{REPORT_EMAIL}}", issues[0]["issue"])

    def test_scaffold_config_creates_jobsearch_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "config").mkdir()
            example = self.repo_root / "config/jobsearch.example.toml"
            (root / "config/jobsearch.example.toml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            templates = root / "profile/templates"
            templates.mkdir(parents=True)
            (templates / "ios.toml").write_text(
                (self.repo_root / "profile/templates/ios.toml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = scaffold_config(root=root)
            self.assertTrue((root / "config/jobsearch.toml").exists())
            self.assertIn(str(root / "config/jobsearch.toml"), result["created"])

    def test_invalid_profile_config_raises(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_profile_config({"profile": {"slug": "ios"}})


if __name__ == "__main__":
    unittest.main()

"""Additional coverage for config loading, local overlays, and profile discovery."""

from __future__ import annotations

import shutil
import tempfile
import unittest
import warnings
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.app_config.loader import (
    DEFAULT_CONFIG_PATH,
    LOCAL_CONFIG_SUFFIX,
    AppConfig,
    load_app_config,
)
from jobtracker.app_config.profiles import JobboardProfile, load_profile, load_profiles
from jobtracker.app_config.schema import (
    ConfigValidationError,
    find_placeholders,
    scan_profile_placeholders,
    validate_jobsearch_config,
    validate_profile_config,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "profile" / "templates" / "generic"

# `profile/` is gitignored, so a fresh clone has no templates to seed a root from.
requires_profile_templates = unittest.skipUnless(
    TEMPLATE_DIR.exists(), "profile/templates is absent from this checkout"
)

BASE_CONFIG = """
schema_version = 1

[paths]
config_dir = "config"
profile_dir = "profile"
output_dir = "outputs/payloads"
payload_dir = "outputs/payloads"

[pipelines.jobboards]
type = "jobboard"
profile = "ios"
providers = ["dou", "workua"]
include_db = true
max_pages = 1

[pipelines.jobboards.notify]
channels = ["email"]

[notify.email]
to = "{{REPORT_EMAIL}}"
from = "{{SMTP_FROM}}"
subject_template = "{subject} — {run_key}"

[store]
backend = "sqlite"
sqlite_path = "outputs/state.sqlite3"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"

[sources.acme]
kind = "jsonld"
listing_url = "https://careers.example.invalid/jobs"

[mail.inbox]
kind = "imap"
"""

LOCAL_CONFIG = """
[paths]
output_dir = "outputs/local-payloads"

[pipelines.jobboards]
providers = ["djinni"]
max_pages = 3

[notify.email]
to = "me@example.com"
"""


class LoadAppConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        (self.root / "config").mkdir()
        self.primary = self.root / DEFAULT_CONFIG_PATH
        self.primary.write_text(BASE_CONFIG, encoding="utf-8")

    @property
    def local_path(self) -> Path:
        return self.primary.with_name(self.primary.stem + LOCAL_CONFIG_SUFFIX)

    def test_loads_the_default_config_path_relative_to_root(self) -> None:
        config = load_app_config(root=self.root)

        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.sources, [self.primary])
        self.assertEqual(config.pipelines["jobboards"]["providers"], ["dou", "workua"])
        self.assertEqual(config.pipelines["jobboards"]["max_pages"], 1)
        self.assertEqual(config.paths["output_dir"], "outputs/payloads")
        self.assertEqual(config.notify["email"]["to"], "{{REPORT_EMAIL}}")
        self.assertEqual(config.schema_version, 1)
        self.assertEqual(config.store["backend"], "sqlite")
        self.assertEqual(config.source_configs["acme"]["kind"], "jsonld")
        self.assertEqual(config.mail["inbox"]["kind"], "imap")

    def test_local_overlay_is_deep_merged_over_the_primary_config(self) -> None:
        self.local_path.write_text(LOCAL_CONFIG, encoding="utf-8")

        config = load_app_config(root=self.root)

        self.assertEqual(config.sources, [self.primary, self.local_path])
        self.assertEqual(config.pipelines["jobboards"]["providers"], ["djinni"])
        self.assertEqual(config.pipelines["jobboards"]["max_pages"], 3)
        self.assertEqual(config.pipelines["jobboards"]["profile"], "ios")
        self.assertEqual(config.pipelines["jobboards"]["notify_channels"], ["email"])
        self.assertEqual(config.paths["output_dir"], "outputs/local-payloads")
        self.assertEqual(config.paths["payload_dir"], "outputs/payloads")
        self.assertEqual(config.notify["email"]["to"], "me@example.com")
        self.assertEqual(config.notify["email"]["from"], "{{SMTP_FROM}}")

    def test_derived_directories_resolve_against_the_root(self) -> None:
        config = load_app_config(root=self.root)

        self.assertEqual(config.config_dir, self.root / "config")
        self.assertEqual(config.profile_dir, self.root / "profile")
        self.assertEqual(config.output_dir, self.root / "outputs/payloads")
        self.assertEqual(config.payload_dir, self.root / "outputs/payloads")
        self.assertEqual(config.store_path, self.root / "outputs/state.sqlite3")
        self.assertEqual(config.artifact_dir, self.root / "outputs/artifacts")

    def test_absolute_configured_paths_remain_absolute(self) -> None:
        config = load_app_config(root=self.root)

        self.assertEqual(config.resolve_path("/tmp/jobsearch-output"), Path("/tmp/jobsearch-output"))

    def test_missing_schema_version_is_accepted_with_a_deprecation_warning(self) -> None:
        self.primary.write_text(BASE_CONFIG.replace("schema_version = 1\n\n", ""), encoding="utf-8")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = load_app_config(root=self.root)

        self.assertEqual(config.schema_version, 1)
        self.assertTrue(any(item.category is DeprecationWarning for item in caught))

    def test_relative_config_paths_are_resolved_against_the_root(self) -> None:
        config = load_app_config("config/jobsearch.toml", root=self.root)

        self.assertEqual(config.sources, [self.primary])

    def test_missing_config_raises_a_validation_error(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_app_config(root=self.root / "elsewhere")


class ValidateJobsearchConfigTests(unittest.TestCase):
    def test_paths_fall_back_to_defaults(self) -> None:
        validated = validate_jobsearch_config({"store": {"backend": "sqlite"}})

        self.assertEqual(validated["paths"]["config_dir"], "config")
        self.assertEqual(validated["paths"]["profile_dir"], "profile")
        self.assertEqual(validated["paths"]["output_dir"], "outputs/automation-payloads")
        self.assertEqual(validated["pipelines"], {})
        self.assertEqual(validated["notify"], {})
        self.assertEqual(validated["schema_version"], 1)
        self.assertEqual(validated["store"]["backend"], "sqlite")
        self.assertEqual(validated["store"]["sqlite_path"], "outputs/jobsearch.sqlite3")
        self.assertEqual(validated["sources"], {})
        self.assertEqual(validated["mail"], {})

    def test_providers_are_required_for_a_pipeline(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config(
                {"pipelines": {"jobboards": {"type": "jobboard", "profile": "generic"}}}
            )

    def test_store_backend_must_be_chosen_explicitly(self) -> None:
        with self.assertRaises(ConfigValidationError) as caught:
            validate_jobsearch_config({})
        self.assertIn("no fallback", str(caught.exception))
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"store": {"backend": "postgres", "transport": "direct"}})
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"store": {"backend": "sqlite", "connector": "postgres_direct"}})
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"store": {"backend": "sqlite", "required_backend": "sqlite"}})
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"store": {"backend": "postgres", "connector": "postgres_direct"}})
        validated = validate_jobsearch_config({"store": {"backend": "supabase", "hosting": "Supabase"}})
        self.assertEqual(validated["store"]["backend"], "postgres")
        self.assertNotIn("connector", validated["store"])
        self.assertEqual(validated["store"]["hosting"], "supabase")

    def test_unknown_schema_version_is_rejected(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"schema_version": 2})

    def test_notify_channel_names_are_normalized(self) -> None:
        validated = validate_jobsearch_config(
            {
                "pipelines": {
                    "jobboards": {
                        "type": "jobboard",
                        "profile": "ios",
                        "providers": ["acme"],
                        "notify": {"channels": [" Email ", "SLACK"]},
                    }
                },
                "notify": {"Email": {"to": "me@example.com"}},
                "store": {"backend": "sqlite"},
            }
        )

        self.assertEqual(validated["pipelines"]["jobboards"]["notify_channels"], ["email", "slack"])
        self.assertEqual(list(validated["notify"]), ["email"])

    def test_unsupported_pipeline_type_is_rejected(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"pipelines": {"x": {"type": "mailbox", "profile": "ios"}}})

    def test_missing_profile_is_rejected(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"pipelines": {"x": {"type": "jobboard"}}})

    def test_empty_provider_list_is_rejected(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config(
                {"pipelines": {"x": {"type": "jobboard", "profile": "ios", "providers": []}}}
            )

    def test_non_table_sections_are_rejected(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_jobsearch_config({"paths": "config"})


@requires_profile_templates
class ProfileLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.profile_dir = self.root / "profile"
        self.profile_dir.mkdir()
        shutil.copyfile(TEMPLATE_DIR / "generic.toml", self.profile_dir / "generic.toml")

    def test_load_profile_reads_a_template_copy(self) -> None:
        profile = load_profile("generic", profile_dir=self.profile_dir)

        self.assertIsInstance(profile, JobboardProfile)
        self.assertEqual(profile.slug, "generic")
        self.assertEqual(profile.name, "Configured job search")
        self.assertEqual(profile.output_slug, "job-search")
        self.assertEqual(profile.email_subject_prefix, "Job search triage")
        self.assertIn("profile/cv.md", profile.profile_files)
        self.assertTrue(profile.evaluation_notes)
        self.assertIsNone(profile.email_to)

    def test_load_profiles_indexes_every_profile_by_slug(self) -> None:
        profiles = load_profiles(self.profile_dir)

        self.assertEqual(set(profiles), {"generic"})
        self.assertEqual(profiles["generic"].output_slug, "job-search")

    def test_load_profiles_skips_example_files(self) -> None:
        (self.profile_dir / "sample.example.toml").write_text(
            "[profile]\nslug = 'sample'\n", encoding="utf-8"
        )

        self.assertEqual(set(load_profiles(self.profile_dir)), {"generic"})

    def test_load_profiles_on_a_missing_directory_is_empty(self) -> None:
        self.assertEqual(load_profiles(self.root / "nope"), {})

    def test_load_profile_reports_a_missing_file(self) -> None:
        with self.assertRaises(ConfigValidationError):
            load_profile("missing", profile_dir=self.profile_dir)

    def test_targets_path_falls_back_to_the_bundled_fixture(self) -> None:
        profile = load_profile("generic", profile_dir=self.profile_dir)

        self.assertTrue(str(profile.targets_path).endswith("provider_targets.toml"))


class ValidateProfileConfigTests(unittest.TestCase):
    def valid(self) -> dict:
        return {
            "schema_version": 1,
            "profile": {
                "slug": "ios",
                "name": "iOS/macOS",
                "output_slug": "ua-jobboards",
                "targets_path": "profile/provider_targets.toml",
                "report_path_template": "outputs/reports/{date}-triage.md",
                "email_body_template": "{date}-email-body.txt",
                "email_subject_prefix": "iOS job triage",
                "profile_files": ["profile/CV_SOURCE.md"],
                "evaluation_notes": ["Senior iOS roles only."],
                "email_to": " me@example.com ",
            },
        }

    def test_valid_profile_is_normalized(self) -> None:
        validated = validate_profile_config(self.valid())

        self.assertEqual(validated["slug"], "ios")
        self.assertEqual(validated["email_to"], "me@example.com")
        self.assertEqual(validated["profile_files"], ["profile/CV_SOURCE.md"])

    def test_blank_email_to_becomes_none(self) -> None:
        data = self.valid()
        data["profile"]["email_to"] = "   "

        self.assertIsNone(validate_profile_config(data)["email_to"])

    def test_versionless_profile_is_accepted_with_a_deprecation_warning(self) -> None:
        data = self.valid()
        data.pop("schema_version")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            validated = validate_profile_config(data)

        self.assertEqual(validated["slug"], "ios")
        self.assertTrue(any(item.category is DeprecationWarning for item in caught))

    def test_unknown_profile_schema_version_is_rejected(self) -> None:
        data = self.valid()
        data["schema_version"] = 2

        with self.assertRaises(ConfigValidationError):
            validate_profile_config(data)

    def test_profile_files_must_be_an_array(self) -> None:
        data = self.valid()
        data["profile"]["profile_files"] = "profile/CV_SOURCE.md"

        with self.assertRaises(ConfigValidationError):
            validate_profile_config(data)

    def test_error_messages_include_the_source_path(self) -> None:
        with self.assertRaises(ConfigValidationError) as caught:
            validate_profile_config({"profile": {"slug": "ios"}}, source_path=Path("profile/ios.toml"))

        self.assertIn("profile/ios.toml", str(caught.exception))


class PlaceholderScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)

    def test_find_placeholders_returns_every_token(self) -> None:
        self.assertEqual(
            find_placeholders("{{OWNER_NAME}} <{{REPORT_EMAIL}}>"),
            ["{{OWNER_NAME}}", "{{REPORT_EMAIL}}"],
        )

    def test_missing_files_are_reported(self) -> None:
        issues = scan_profile_placeholders(["profile/absent.md"], root=self.root)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["issue"], "profile file does not exist")

    def test_resolved_files_produce_no_issues(self) -> None:
        (self.root / "profile").mkdir()
        (self.root / "profile" / "cv.md").write_text(
            "Fictitious candidate — software engineer", encoding="utf-8"
        )

        self.assertEqual(scan_profile_placeholders(["profile/cv.md"], root=self.root), [])

    def test_duplicate_placeholders_are_deduplicated_in_the_message(self) -> None:
        (self.root / "cv.md").write_text("{{REPORT_EMAIL}} and {{REPORT_EMAIL}}", encoding="utf-8")

        issues = scan_profile_placeholders(["cv.md"], root=self.root)

        self.assertEqual(issues[0]["issue"], "unresolved placeholders: {{REPORT_EMAIL}}")


if __name__ == "__main__":
    unittest.main()

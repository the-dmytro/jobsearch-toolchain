from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from jobtracker.provider_fetch import collect_provider_run
from jobtracker.validation import validate_payload

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"


class PublicContractTests(unittest.TestCase):
    def schema(self, name: str) -> dict:
        schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return schema

    def test_config_contract_accepts_local_first_config(self) -> None:
        config = {
            "schema_version": 1,
            "store": {"backend": "sqlite", "sqlite_path": "outputs/jobsearch.sqlite3"},
            "pipelines": {
                "demo": {
                    "type": "jobboard",
                    "profile": "generic",
                    "providers": ["example"],
                }
            },
        }

        Draft202012Validator(self.schema("jobsearch-config.v1.schema.json")).validate(config)

    def test_shipped_config_and_profile_templates_validate(self) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib

        config = tomllib.loads((ROOT / "config/jobsearch.example.toml").read_text(encoding="utf-8"))
        profile = tomllib.loads((ROOT / "profile/templates/generic/generic.toml").read_text(encoding="utf-8"))

        Draft202012Validator(self.schema("jobsearch-config.v1.schema.json")).validate(config)
        Draft202012Validator(self.schema("profile-config.v1.schema.json")).validate(profile)

    def test_profile_contract_accepts_a_neutral_profile(self) -> None:
        profile = {
            "schema_version": 1,
            "profile": {
                "slug": "generic",
                "name": "Generic profile",
                "output_slug": "job-search",
                "targets_path": "profile/provider_targets.toml",
                "report_path_template": "outputs/reports/{date}.md",
                "email_body_template": "profile/email_body.md",
                "email_subject_prefix": "Job search report",
                "profile_files": ["profile/cv.md", "profile/preferences.md"],
            },
        }

        Draft202012Validator(self.schema("profile-config.v1.schema.json")).validate(profile)

    def test_payload_contract_rejects_legacy_only_payload(self) -> None:
        validator = Draft202012Validator(self.schema("automation-payload.v1.schema.json"))

        errors = list(validator.iter_errors({"run": {"run_key": "x", "status": "completed"}, "jobs": []}))

        self.assertTrue(errors)

    def test_legacy_aliases_normalize_to_payload_v1_with_warnings(self) -> None:
        result = validate_payload(
            {
                "run": {"run_key": "fixture-legacy-1", "status": "completed"},
                "emails": [],
                "jobs": [
                    {
                        "title": "Software Engineer",
                        "external_id": "fixture-1",
                        "source_url": "https://jobs.example.invalid/fixture-1",
                    }
                ],
            },
            provider="fixture",
        )

        self.assertTrue(result.ok)
        self.assertTrue(any("legacy" in warning for warning in result.warnings))
        Draft202012Validator(self.schema("automation-payload.v1.schema.json")).validate(result.normalized)

    def test_deterministic_source_producer_emits_payload_v1(self) -> None:
        result = collect_provider_run(
            "greenhouse",
            dry_run=True,
            fixture_dir=ROOT / "jobtracker/fixtures/provider_fetch",
            targets_path=ROOT / "profile/templates/generic/provider_targets.toml",
            now=datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc),
            max_boards=1,
        )

        Draft202012Validator(self.schema("automation-payload.v1.schema.json")).validate(result.payload)

    def test_doctor_contract_accepts_versioned_report(self) -> None:
        report = {
            "schema_version": 1,
            "status": "ready",
            "ok": True,
            "issues": [],
            "checks": {"config": []},
        }

        Draft202012Validator(self.schema("doctor-report.v1.schema.json")).validate(report)


if __name__ == "__main__":
    unittest.main()

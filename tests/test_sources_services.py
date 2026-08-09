"""Fixture-mode collection runs for the in-tree service connectors.

These exercise the full ``collect_provider_run`` path — target loading, fetcher
selection, lane filtering, payload building — against the bundled fixtures, so
no network access is required.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jobtracker.provider_fetch import collect_provider_run
from jobtracker.sources.registry import source_registry
from jobtracker.sources.services.ashby import AshbySource
from jobtracker.sources.services.lever import LeverSource

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "jobtracker" / "fixtures" / "provider_fetch"
TARGETS_PATH = REPO_ROOT / "jobtracker" / "fixtures" / "provider_targets.toml"
NOW = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)


def _registered_slugs() -> set[str]:
    registry = source_registry
    entries = registry.all() if hasattr(registry, "all") else registry
    return set(entries)


class ServiceSourceRegistrationTests(unittest.TestCase):
    def test_builtin_service_connectors_are_registered(self) -> None:
        self.assertLessEqual(
            {"ashby", "djinni", "dou", "greenhouse", "lever", "workua"},
            _registered_slugs(),
        )

    def test_board_backed_connectors_declare_api_templates(self) -> None:
        self.assertIn("{token}", AshbySource.api_url_template)
        self.assertIn("{token}", LeverSource.api_url_template)
        self.assertEqual(AshbySource.jobs_key, "jobs")
        self.assertIsNone(LeverSource.jobs_key)


class BoardFixtureRunTests(unittest.TestCase):
    def collect(self, provider: str, payload_out: Path | None = None):
        return collect_provider_run(
            provider,
            conn=None,
            dry_run=True,
            payload_out=payload_out,
            fixture_dir=FIXTURE_DIR,
            targets_path=TARGETS_PATH,
            now=NOW,
            board_tokens=["default"],
            max_boards=1,
        )

    def assert_fixture_run(self, result, provider: str) -> None:
        self.assertEqual(result.provider_slug, provider)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.blockers, [])
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertEqual(result.metrics.board_tokens, ["default"])
        self.assertEqual(result.metrics.jobs_emitted, len(result.candidates))
        self.assertGreaterEqual(result.metrics.jobs_skipped_by_filter, 0)
        self.assertEqual(result.run_key, f"{provider}-discovery-20260429T090000Z")

    def test_ashby_fixture_run_completes_with_candidates(self) -> None:
        result = self.collect("ashby")

        self.assert_fixture_run(result, "ashby")
        candidate = result.candidates[0]
        self.assertTrue(candidate.external_id.startswith("ashby:default:"))
        self.assertIn("ashbyhq.com", candidate.source_url)
        self.assertEqual(candidate.location, "Remote — EMEA")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.seniority, "Senior")
        self.assertEqual(candidate.metadata["board_token"], "default")

    def test_lever_fixture_run_completes_with_candidates(self) -> None:
        result = self.collect("lever")

        self.assert_fixture_run(result, "lever")
        candidate = result.candidates[0]
        self.assertTrue(candidate.external_id.startswith("lever:default:"))
        self.assertIn("jobs.lever.co", candidate.source_url)
        self.assertEqual(candidate.location, "Remote")
        self.assertEqual(candidate.work_model, "Remote")

    def test_dry_run_payload_matches_the_automation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_out = Path(temp_dir) / "ashby.payload.json"

            result = self.collect("ashby", payload_out=payload_out)
            payload = json.loads(payload_out.read_text(encoding="utf-8"))

            self.assertFalse(result.persisted)
            self.assertEqual(result.payload_path, payload_out)
            self.assertEqual(payload["run"]["run_key"], result.run_key)
            self.assertEqual(payload["run"]["status"], "completed")
            self.assertEqual(len(payload["opportunities"]), len(result.candidates))
            self.assertEqual(len(payload["source_items"]), len(result.candidates))
            for opportunity in payload["opportunities"]:
                self.assertEqual(opportunity["opportunity_type"], "employment")
                self.assertTrue(opportunity["title"])
                self.assertTrue(opportunity["source_url"])

    def test_result_to_dict_summarizes_the_run(self) -> None:
        summary = self.collect("lever").to_dict(dry_run=True)

        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["provider"], "lever")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["opportunities"], summary["source_items"])
        self.assertEqual(summary["metrics"]["run_status"], "completed")
        self.assertIsNone(summary["payload_path"])

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(Exception) as caught:
            collect_provider_run(
                "definitely-not-a-provider",
                conn=None,
                dry_run=True,
                fixture_dir=FIXTURE_DIR,
                targets_path=TARGETS_PATH,
                now=NOW,
            )
        self.assertIn("definitely-not-a-provider", str(caught.exception))


class GreenhouseFixtureRunTests(unittest.TestCase):
    def test_greenhouse_board_token_run(self) -> None:
        result = collect_provider_run(
            "greenhouse",
            conn=None,
            dry_run=True,
            fixture_dir=FIXTURE_DIR,
            targets_path=TARGETS_PATH,
            now=NOW,
            board_tokens=["oura"],
            max_boards=1,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.metrics.board_tokens, ["oura"])
        self.assertGreaterEqual(len(result.candidates), 1)


if __name__ == "__main__":
    unittest.main()

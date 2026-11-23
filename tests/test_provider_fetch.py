from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from jobtracker.provider_fetch import _matches_lane, benchmark_providers, collect_provider_run

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "jobtracker" / "fixtures" / "provider_fetch"
NOW = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)


class ProviderFetchTests(unittest.TestCase):
    def test_lane_rules_can_exclude_senior_domain_roles(self) -> None:
        lane = {
            "include_terms": ["data engineer", "python engineer"],
            "exclude_terms": ["senior data", "senior python"],
        }

        self.assertFalse(_matches_lane("Senior Python Engineer", lane))
        self.assertFalse(_matches_lane("Senior ML Engineer", lane))
        self.assertFalse(_matches_lane("Senior Data Engineer", lane))
        self.assertTrue(_matches_lane("Python Engineer with AI focus", lane))
        self.assertTrue(_matches_lane("Junior Data Engineer", lane))

    def test_dou_fixture_run_parses_and_enriches_one_ios_job(self) -> None:
        result = collect_provider_run("dou", dry_run=True, fixture_dir=FIXTURE_DIR, now=NOW, detail_limit=1)

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.external_id, "companies/acme/vacancies/123456")
        self.assertEqual(candidate.title, "Senior iOS Engineer")
        self.assertEqual(candidate.company, "Acme")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.engagement_type, "Full-time")
        self.assertEqual(candidate.compensation_text, "EUR 85000")

    def test_workua_fixture_run_parses_numeric_job_id(self) -> None:
        result = collect_provider_run(
            "workua", dry_run=True, fixture_dir=FIXTURE_DIR, now=NOW, detail_limit=1
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.external_id, "7971690")
        self.assertEqual(candidate.company, "Acme Mobile")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.seniority, "Junior")

    def test_djinni_fixture_run_uses_json_ld(self) -> None:
        result = collect_provider_run(
            "djinni", dry_run=True, fixture_dir=FIXTURE_DIR, now=NOW, detail_limit=1
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.external_id, "822108")
        self.assertEqual(candidate.company, "QIT Software")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.compensation_text, "USD 5000-7000")

    def test_greenhouse_fixture_run_uses_board_api(self) -> None:
        result = collect_provider_run(
            "greenhouse",
            dry_run=True,
            fixture_dir=FIXTURE_DIR,
            now=NOW,
            board_tokens=["oura"],
            max_boards=1,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.external_id, "gh:oura:4024449009")
        self.assertEqual(candidate.company, "Ōura")
        self.assertEqual(candidate.location, "Remote, Europe")
        self.assertEqual(result.metrics.api_request_count, 1)

    def test_fixture_benchmark_runs_all_collectors(self) -> None:
        payload = benchmark_providers(
            ["dou", "workua", "djinni", "greenhouse"],
            live=False,
            fixture_dir=FIXTURE_DIR,
            now=NOW,
            detail_limit=1,
            max_boards=1,
        )

        self.assertEqual(payload["mode"], "fixture")
        self.assertEqual(len(payload["results"]), 4)
        self.assertTrue(all(result["status"] in {"completed", "partial"} for result in payload["results"]))


if __name__ == "__main__":
    unittest.main()

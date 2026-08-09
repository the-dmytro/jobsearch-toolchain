from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jobtracker.db import connect_test
from jobtracker.greenhouse_import import import_greenhouse_tracking
from jobtracker.legacy_import import import_legacy_csv
from jobtracker.linkedin_import import import_linkedin_tracking
from jobtracker.migrations import apply_migrations
from jobtracker.payloads import check_duplicates, upsert_run_payload
from jobtracker.provider_fetch import collect_provider_run

LEGACY_HEADER = [
    "Company",
    "Location",
    "Kind",
    "Domain",
    "Vacancy link",
    "Source",
    "Application date",
    "Salary requested",
    "Stage",
    "Decline reason",
    "Passed",
    "Notes",
]

LINKEDIN_APP_HEADER = [
    "stage",
    "company",
    "role",
    "location",
    "work_model",
    "job_link",
    "applied_approx",
    "posting_status",
    "extra_info",
]

GREENHOUSE_HEADER = [
    "stage",
    "company",
    "role",
    "location",
    "work_model",
    "application_link",
    "applied_approx",
    "posting_status",
    "extra_info",
]

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "jobtracker" / "fixtures" / "provider_fetch"
FIXTURE_NOW = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]], delimiter: str = ",") -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def _test_db_reachable() -> bool:
    if not os.getenv("SUPABASE_TEST_DB_URL"):
        return False
    try:
        with connect_test() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
        return True
    except Exception:
        return False


def _bootstrap_plain_postgres(conn) -> None:
    bootstrap = Path(__file__).resolve().parent.parent / "db" / "ci" / "plain_postgres_bootstrap.sql"
    if not bootstrap.exists():
        return
    with conn.cursor() as cur:
        cur.execute(bootstrap.read_text(encoding="utf-8"))
    conn.commit()


@unittest.skipUnless(_test_db_reachable(), "SUPABASE_TEST_DB_URL must point at a reachable database")
class DbIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with connect_test() as conn:
            _bootstrap_plain_postgres(conn)
            apply_migrations(conn)

    def setUp(self) -> None:
        with connect_test() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    truncate table
                      application_events,
                      interview_contacts,
                      interviews,
                      communications,
                      contacts,
                      insights,
                      document_chunks,
                      legacy_import_rows,
                      evaluations,
                      source_items,
                      automation_runs,
                      artifacts,
                      applications,
                      opportunities,
                      organizations,
                      providers
                    restart identity cascade
                    """
                )
            conn.commit()

    def test_imports_payloads_duplicates_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_csv = root / "legacy.csv"
            linkedin_jobs = root / "linkedin_jobs.csv"
            linkedin_active = root / "linkedin_active.csv"
            linkedin_archived = root / "linkedin_archived.csv"
            greenhouse_csv = root / "greenhouse.csv"
            payload_path = root / "payload.json"

            write_csv(
                legacy_csv,
                LEGACY_HEADER,
                [
                    {
                        "Company": "Legacy Test Co",
                        "Location": "Barcelona",
                        "Kind": "Hybrid",
                        "Domain": "Product",
                        "Vacancy link": "https://www.linkedin.com/jobs/view/1111111111/?trackingId=abc",
                        "Source": "LinkedIn",
                        "Application date": "4 Feb 2025",
                        "Salary requested": "EUR 70000",
                        "Stage": "Applied",
                        "Decline reason": "",
                        "Passed": "",
                        "Notes": "integration sample",
                    }
                ],
                delimiter=";",
            )
            write_csv(
                linkedin_jobs,
                [
                    "record_id",
                    "company",
                    "role_title",
                    "linkedin_job_id",
                    "job_url",
                    "application_url",
                    "location",
                    "work_model",
                    "employment_type",
                    "seniority",
                    "company_domain",
                    "source_status",
                    "first_seen",
                    "last_seen",
                    "score",
                    "confidence",
                    "recommendation",
                    "priority",
                    "status",
                    "main_match",
                    "main_risks",
                    "missing_information",
                    "positioning_angle",
                    "salary_expectation",
                    "action_next",
                    "manual_review_reason",
                ],
                [
                    {
                        "record_id": "li-test-1",
                        "company": "LinkedIn Test Co",
                        "role_title": "Senior iOS Engineer",
                        "linkedin_job_id": "2222222222",
                        "job_url": "https://www.linkedin.com/jobs/view/2222222222/?trackingId=x",
                        "application_url": "https://example.com/apply",
                        "location": "Remote",
                        "work_model": "Remote",
                        "employment_type": "Full-time",
                        "seniority": "Senior",
                        "company_domain": "example.com",
                        "source_status": "open",
                        "first_seen": "2026-04-28T08:00:00Z",
                        "last_seen": "2026-04-28T08:00:00Z",
                        "score": "8",
                        "confidence": "High",
                        "recommendation": "Apply",
                        "priority": "P1",
                        "status": "apply",
                        "main_match": "Strong iOS fit",
                        "main_risks": "Unknown salary",
                        "missing_information": "",
                        "positioning_angle": "Senior iOS delivery",
                        "salary_expectation": "EUR 80k",
                        "action_next": "Apply",
                        "manual_review_reason": "",
                    }
                ],
            )
            write_csv(
                linkedin_active,
                LINKEDIN_APP_HEADER,
                [
                    {
                        "stage": "Applied",
                        "company": "LinkedIn Active Co",
                        "role": "iOS Engineer",
                        "location": "Madrid",
                        "work_model": "Hybrid",
                        "job_link": "https://www.linkedin.com/jobs/view/3333333333/",
                        "applied_approx": "1 day ago",
                        "posting_status": "Open",
                        "extra_info": "",
                    }
                ],
            )
            write_csv(
                linkedin_archived,
                LINKEDIN_APP_HEADER,
                [
                    {
                        "stage": "Archived",
                        "company": "LinkedIn Archived Co",
                        "role": "iOS Engineer",
                        "location": "Remote",
                        "work_model": "Remote",
                        "job_link": "https://www.linkedin.com/jobs/view/4444444444/",
                        "applied_approx": "2 days ago",
                        "posting_status": "Closed",
                        "extra_info": "Rejected",
                    }
                ],
            )
            write_csv(
                greenhouse_csv,
                GREENHOUSE_HEADER,
                [
                    {
                        "stage": "Greenhouse",
                        "company": "Greenhouse Test Co",
                        "role": "Senior iOS Engineer",
                        "location": "Barcelona",
                        "work_model": "Hybrid",
                        "application_link": "https://my.greenhouse.io/applications/55555555?utm_source=x",
                        "applied_approx": "3 days ago",
                        "posting_status": "Inactive",
                        "extra_info": "Closed",
                    }
                ],
            )
            payload_path.write_text(
                json.dumps(
                    {
                        "run": {
                            "run_key": "test-upwork-run",
                            "started_at": "2026-04-28T10:00:00Z",
                            "finished_at": "2026-04-28T10:01:00Z",
                            "status": "completed",
                            "summary": "integration sample",
                            "report_email_sent": False,
                        },
                        "source_items": [
                            {
                                "source_type": "email",
                                "external_id": "email-test-1",
                                "source_url": "https://mail.google.com/mail/#all/email-test-1",
                                "timestamp": "2026-04-28T10:00:00Z",
                                "subject": "Sample Upwork job",
                                "summary": "Sample email",
                            }
                        ],
                        "opportunities": [
                            {
                                "opportunity_type": "freelance_project",
                                "external_id": "upwork-test-1",
                                "title": "Fix iOS App Bug",
                                "source_url": "https://www.upwork.com/jobs/~upwork-test-1",
                                "apply_url": "https://www.upwork.com/jobs/~upwork-test-1",
                                "location": "Remote",
                                "work_model": "Remote",
                                "engagement_type": "Hourly",
                                "domain": "iOS maintenance",
                                "evaluation": {
                                    "verdict": "Apply",
                                    "confidence": "High",
                                    "main_match": "Narrow iOS bugfix",
                                    "main_risks": "Unknown client history",
                                    "pricing_recommendation": "$45/hr",
                                    "action_next": "Review manually",
                                },
                                "source_items": ["email-test-1"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with connect_test() as conn:
                first_legacy = import_legacy_csv(conn, legacy_csv)
                second_legacy = import_legacy_csv(conn, legacy_csv)
                first_linkedin = import_linkedin_tracking(
                    conn, jobs_csv=linkedin_jobs, active_csv=linkedin_active, archived_csv=linkedin_archived
                )
                second_linkedin = import_linkedin_tracking(
                    conn, jobs_csv=linkedin_jobs, active_csv=linkedin_active, archived_csv=linkedin_archived
                )
                first_greenhouse = import_greenhouse_tracking(conn, csv_path=greenhouse_csv)
                second_greenhouse = import_greenhouse_tracking(conn, csv_path=greenhouse_csv)
                first_payload = upsert_run_payload(conn, "upwork", payload_path)
                second_payload = upsert_run_payload(conn, "upwork", payload_path)
                dupes = check_duplicates(conn, "upwork", None, None, external_id="upwork-test-1")

                with conn.cursor() as cur:
                    cur.execute("select count(*) as count from opportunities")
                    opportunity_count = cur.fetchone()["count"]
                    cur.execute("select count(*) as count from applications")
                    application_count = cur.fetchone()["count"]
                    cur.execute("select count(*) as count from automation_runs")
                    run_count = cur.fetchone()["count"]

            self.assertEqual(first_legacy["created_or_updated"], 1)
            self.assertEqual(second_legacy["created_or_updated"], 1)
            self.assertEqual(first_linkedin["jobs"], 1)
            self.assertEqual(second_linkedin["applications"], 2)
            self.assertEqual(first_greenhouse["applications"], 1)
            self.assertEqual(second_greenhouse["inactive_declined_applications"], 1)
            self.assertEqual(first_payload["opportunities"], 1)
            self.assertEqual(second_payload["evaluations"], 1)
            self.assertEqual(len(dupes), 1)
            self.assertEqual(opportunity_count, 6)
            self.assertEqual(application_count, 4)
            self.assertEqual(run_count, 1)

    def test_provider_collectors_upsert_and_skip_duplicates(self) -> None:
        with connect_test() as conn:
            first_dou = collect_provider_run(
                "dou", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            second_dou = collect_provider_run(
                "dou", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            first_workua = collect_provider_run(
                "workua", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            second_workua = collect_provider_run(
                "workua", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            first_djinni = collect_provider_run(
                "djinni", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            second_djinni = collect_provider_run(
                "djinni", conn=conn, dry_run=False, fixture_dir=FIXTURE_DIR, now=FIXTURE_NOW, detail_limit=1
            )
            first_greenhouse = collect_provider_run(
                "greenhouse",
                conn=conn,
                dry_run=False,
                fixture_dir=FIXTURE_DIR,
                now=FIXTURE_NOW,
                board_tokens=["oura"],
                max_boards=1,
            )
            second_greenhouse = collect_provider_run(
                "greenhouse",
                conn=conn,
                dry_run=False,
                fixture_dir=FIXTURE_DIR,
                now=FIXTURE_NOW,
                board_tokens=["oura"],
                max_boards=1,
            )

            with conn.cursor() as cur:
                cur.execute("select count(*) as count from providers")
                provider_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from opportunities")
                opportunity_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from source_items")
                source_item_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from automation_runs")
                run_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from applications")
                application_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from evaluations")
                evaluation_count = cur.fetchone()["count"]

        self.assertTrue(first_dou.persisted)
        self.assertTrue(first_workua.persisted)
        self.assertTrue(first_djinni.persisted)
        self.assertTrue(first_greenhouse.persisted)
        self.assertEqual(second_dou.metrics.detail_request_count, 0)
        self.assertEqual(second_workua.metrics.detail_request_count, 0)
        self.assertEqual(second_djinni.metrics.detail_request_count, 0)
        self.assertEqual(second_greenhouse.metrics.api_request_count, 1)
        self.assertEqual(first_greenhouse.metrics.api_request_count, 1)
        self.assertEqual(provider_count, 4)
        self.assertEqual(opportunity_count, 4)
        self.assertEqual(source_item_count, 4)
        self.assertEqual(run_count, 4)
        self.assertEqual(application_count, 0)
        self.assertEqual(evaluation_count, 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from jobtracker.linkedin_import import (
    build_linkedin_application_records,
    linkedin_job_id_from_url,
    parse_applied_approx,
    summarize_linkedin_tracking,
)
from jobtracker.url_tools import clean_url

APP_HEADER = [
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


class LinkedInImportTests(unittest.TestCase):
    def write_csv(self, fieldnames: list[str], rows: list[dict[str, str]]) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", newline="", suffix=".csv", delete=False, encoding="utf-8")
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return Path(tmp.name)

    def test_archived_applications_are_declined(self) -> None:
        archived = self.write_csv(
            APP_HEADER,
            [
                {
                    "stage": "Archived",
                    "company": "Trainline",
                    "role": "Senior iOS Engineer",
                    "location": "Barcelona",
                    "work_model": "Hybrid",
                    "job_link": "https://www.linkedin.com/jobs/view/4315838390/?trackingId=abc",
                    "applied_approx": "2mo ago",
                    "posting_status": "Closed",
                    "extra_info": "Not moving forward",
                }
            ],
        )
        records, skipped = build_linkedin_application_records(
            active_path="missing.csv", archived_path=archived, as_of=date(2026, 4, 27)
        )
        self.assertEqual(skipped, [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "declined")
        self.assertEqual(records[0].current_stage, "Declined")
        self.assertEqual(records[0].outcome, "declined")
        self.assertEqual(records[0].decline_reason, "Not moving forward")
        self.assertEqual(records[0].applied_at.isoformat(), "2026-02-27")
        self.assertEqual(records[0].linkedin_job_id, "4315838390")
        self.assertEqual(records[0].job_url, "https://www.linkedin.com/jobs/view/4315838390/")

    def test_summary_counts_archived_declines(self) -> None:
        active = self.write_csv(
            APP_HEADER,
            [
                {
                    "stage": "Applied",
                    "company": "Proxify",
                    "role": "Senior iOS Developer",
                    "location": "EMEA",
                    "work_model": "Remote",
                    "job_link": "https://www.linkedin.com/jobs/view/4303037177/",
                    "applied_approx": "1w ago",
                    "posting_status": "Open",
                    "extra_info": "",
                }
            ],
        )
        archived = self.write_csv(
            APP_HEADER,
            [
                {
                    "stage": "Archived",
                    "company": "italki",
                    "role": "iOS Developer",
                    "location": "Madrid",
                    "work_model": "Hybrid",
                    "job_link": "https://www.linkedin.com/jobs/view/4361569206/",
                    "applied_approx": "3mo ago",
                    "posting_status": "Closed",
                    "extra_info": "",
                }
            ],
        )
        summary = summarize_linkedin_tracking(
            jobs_csv="missing.csv", active_csv=active, archived_csv=archived, as_of=date(2026, 4, 27)
        )
        self.assertEqual(summary["application_rows"], 2)
        self.assertEqual(summary["active_application_rows"], 1)
        self.assertEqual(summary["archived_application_rows"], 1)
        self.assertEqual(summary["declined_from_archived_rows"], 1)
        self.assertEqual(summary["application_statuses"]["declined"], 1)

    def test_linkedin_url_helpers(self) -> None:
        self.assertEqual(
            linkedin_job_id_from_url(
                "https://es.linkedin.com/jobs/view/senior-ios-developer-at-example-4397405467"
            ),
            "4397405467",
        )
        self.assertEqual(
            clean_url(
                "https://es.linkedin.com/jobs/view/senior-ios-developer-at-example-4397405467?trackingId=x"
            ),
            "https://www.linkedin.com/jobs/view/4397405467/",
        )
        self.assertEqual(parse_applied_approx("3d ago", date(2026, 4, 27)).isoformat(), "2026-04-24")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.greenhouse_import import (
    build_greenhouse_application_records,
    greenhouse_application_id_from_url,
    summarize_greenhouse_tracking,
)

HEADER = [
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


class GreenhouseImportTests(unittest.TestCase):
    def write_csv(self, rows: list[dict[str, str]]) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", newline="", suffix=".csv", delete=False, encoding="utf-8")
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=HEADER)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return Path(tmp.name)

    def test_active_and_inactive_greenhouse_rows_are_parsed(self) -> None:
        path = self.write_csv(
            [
                {
                    "stage": "Greenhouse",
                    "company": "Skyscanner",
                    "role": "Software Engineer 2 - Mobile (iOS)",
                    "location": "Barcelona",
                    "work_model": "Hybrid",
                    "application_link": "https://my.greenhouse.io/applications/40658372?utm_source=x&gh_src=abc",
                    "applied_approx": "33 days ago",
                    "posting_status": "Active",
                    "extra_info": "",
                },
                {
                    "stage": "Greenhouse",
                    "company": "BLACKLANE",
                    "role": "Senior Software Engineer - iOS",
                    "location": "Barcelona",
                    "work_model": "[NEEDS INPUT]",
                    "application_link": "https://my.greenhouse.io/applications/38955837",
                    "applied_approx": "41 days ago",
                    "posting_status": "Inactive",
                    "extra_info": "Closed after applying",
                },
            ]
        )

        records, skipped = build_greenhouse_application_records(path, as_of=date(2026, 4, 27))

        self.assertEqual(skipped, [])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].greenhouse_application_id, "40658372")
        self.assertEqual(records[0].external_id, "application:40658372")
        self.assertEqual(records[0].application_url, "https://my.greenhouse.io/applications/40658372")
        self.assertEqual(records[0].applied_at.isoformat(), "2026-03-25")
        self.assertEqual(records[0].status, "applied")
        self.assertEqual(records[1].work_model, None)
        self.assertEqual(records[1].status, "declined")
        self.assertEqual(records[1].current_stage, "Declined")
        self.assertEqual(records[1].outcome, "declined")
        self.assertEqual(records[1].decline_reason, "Closed after applying")

    def test_summary_counts_inactive_rows_as_declined(self) -> None:
        path = self.write_csv(
            [
                {
                    "stage": "Greenhouse",
                    "company": "Monzo",
                    "role": "Senior iOS Engineer",
                    "location": "Barcelona",
                    "work_model": "Hybrid",
                    "application_link": "https://my.greenhouse.io/applications/40655282",
                    "applied_approx": "33 days ago",
                    "posting_status": "Active",
                    "extra_info": "",
                },
                {
                    "stage": "Greenhouse",
                    "company": "Sporty Group",
                    "role": "Lead iOS Engineer",
                    "location": "Global",
                    "work_model": "Remote",
                    "application_link": "https://my.greenhouse.io/applications/27648208",
                    "applied_approx": "101 days ago",
                    "posting_status": "Inactive",
                    "extra_info": "",
                },
            ]
        )

        summary = summarize_greenhouse_tracking(path, as_of=date(2026, 4, 27))

        self.assertEqual(summary["application_rows"], 2)
        self.assertEqual(summary["active_rows"], 1)
        self.assertEqual(summary["inactive_rows"], 1)
        self.assertEqual(summary["declined_from_inactive_rows"], 1)
        self.assertEqual(summary["application_statuses"]["declined"], 1)

    def test_greenhouse_application_id_from_url(self) -> None:
        self.assertEqual(
            greenhouse_application_id_from_url("https://my.greenhouse.io/applications/44804184?x=1"),
            "44804184",
        )


if __name__ == "__main__":
    unittest.main()

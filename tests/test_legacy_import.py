from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobtracker.legacy_import import build_legacy_records, summarize_legacy_csv
from jobtracker.pdf_links import PdfLink
from jobtracker.url_tools import clean_url
from jobtracker.utils import parse_money_range, valid_url

HEADER = [
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


class LegacyImportTests(unittest.TestCase):
    def write_csv(self, rows: list[dict[str, str]]) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", newline="", suffix=".csv", delete=False, encoding="utf-8")
        with tmp:
            writer = csv.DictWriter(tmp, fieldnames=HEADER, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return Path(tmp.name)

    def test_build_records_skips_empty_company_and_preserves_placeholder_link(self) -> None:
        path = self.write_csv(
            [
                {
                    "Company": "Primer",
                    "Location": "EMEA",
                    "Kind": "Remote",
                    "Domain": "Payments",
                    "Vacancy link": "Link",
                    "Source": "LinkedIn",
                    "Application date": "4 Feb 2025",
                    "Salary requested": "€\t68.000",
                    "Stage": "Rejected",
                    "Decline reason": "Other candidates",
                    "Passed": "",
                    "Notes": "",
                },
                {
                    "Company": "",
                    "Location": "",
                    "Kind": "",
                    "Domain": "",
                    "Vacancy link": "",
                    "Source": "",
                    "Application date": "",
                    "Salary requested": "",
                    "Stage": "Applied",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
            ]
        )
        records, skipped = build_legacy_records(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(records[0].provider_slug, "linkedin")
        self.assertIsNone(records[0].source_url)
        self.assertIn("legacy_link_placeholder_or_non_url", records[0].warnings)
        self.assertEqual(records[0].applied_at.isoformat(), "2025-02-04")
        self.assertEqual(records[0].salary["currency"], "EUR")
        self.assertEqual(str(records[0].salary["min"]), "68000")

    def test_summary_counts_provider_stage_and_warnings(self) -> None:
        path = self.write_csv(
            [
                {
                    "Company": "Example Motors",
                    "Location": "Remote",
                    "Kind": "Hybrid",
                    "Domain": "Automotive",
                    "Vacancy link": "https://example.com/job",
                    "Source": "Other",
                    "Application date": "31 Jan 2025",
                    "Salary requested": "€\t65.000",
                    "Stage": "Declined",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
                {
                    "Company": "Djinni Co",
                    "Location": "Ukraine",
                    "Kind": "Remote",
                    "Domain": "Product",
                    "Vacancy link": "Link 1, link 2",
                    "Source": "Djinny",
                    "Application date": "3 Feb 2025",
                    "Salary requested": "",
                    "Stage": "Applied",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
            ]
        )
        summary = summarize_legacy_csv(path)
        self.assertEqual(summary["usable_rows"], 2)
        self.assertEqual(summary["providers"]["other"], 1)
        self.assertEqual(summary["providers"]["djinni"], 1)
        self.assertEqual(summary["stages"]["Applied"], 1)
        self.assertEqual(summary["warnings"]["legacy_link_placeholder_or_non_url"], 1)

    def test_pdf_links_fill_placeholder_rows_and_clean_csv_urls(self) -> None:
        path = self.write_csv(
            [
                {
                    "Company": "Primer",
                    "Location": "EMEA",
                    "Kind": "Remote",
                    "Domain": "Payments",
                    "Vacancy link": "Link",
                    "Source": "LinkedIn",
                    "Application date": "4 Feb 2025",
                    "Salary requested": "",
                    "Stage": "Rejected",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
                {
                    "Company": "Dual Link Co",
                    "Location": "Remote",
                    "Kind": "Remote",
                    "Domain": "AI",
                    "Vacancy link": "Link 1, link 2",
                    "Source": "LinkedIn",
                    "Application date": "5 Feb 2025",
                    "Salary requested": "",
                    "Stage": "Applied",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
                {
                    "Company": "CSV Link Co",
                    "Location": "Remote",
                    "Kind": "Remote",
                    "Domain": "Tools",
                    "Vacancy link": "https://example.com/job?utm_source=mail&job=123",
                    "Source": "Manual",
                    "Application date": "6 Feb 2025",
                    "Salary requested": "",
                    "Stage": "Applied",
                    "Decline reason": "",
                    "Passed": "",
                    "Notes": "",
                },
            ]
        )
        fake_links = [
            PdfLink(
                "https://www.linkedin.com/jobs/view/111/",
                "https://www.linkedin.com/jobs/view/111/?trackingId=abc",
                1,
                1,
                (512.0,),
            ),
            PdfLink(
                "https://jobs.example.com/a", "https://jobs.example.com/a?utm_campaign=x", 1, 2, (512.0,)
            ),
            PdfLink("https://jobs.example.com/b", "https://jobs.example.com/b?refId=x", 1, 3, (512.0,)),
        ]

        with patch("jobtracker.legacy_import.extract_pdf_links", return_value=fake_links):
            records, skipped = build_legacy_records(path, links_pdf="links.pdf")

        self.assertEqual(skipped, [])
        self.assertEqual(records[0].source_url, "https://www.linkedin.com/jobs/view/111/")
        self.assertEqual(records[1].link_urls, ["https://jobs.example.com/a", "https://jobs.example.com/b"])
        self.assertEqual(records[2].source_url, "https://example.com/job?job=123")
        self.assertEqual(records[0].link_sources[0]["source"], "pdf_annotation")
        self.assertEqual(records[2].link_sources[0]["source"], "csv")

    def test_url_and_money_helpers(self) -> None:
        self.assertEqual(valid_url("https://example.com/a"), "https://example.com/a")
        self.assertIsNone(valid_url("Link 1, link 2"))
        self.assertEqual(
            clean_url("https://www.linkedin.com/jobs/view/123/?trackingId=x"),
            "https://www.linkedin.com/jobs/view/123/",
        )
        self.assertEqual(
            clean_url("https://example.com/job?utm_source=x&id=7&trk=y"), "https://example.com/job?id=7"
        )
        salary = parse_money_range("$90000-100000")
        self.assertEqual(salary["currency"], "USD")
        self.assertEqual(str(salary["min"]), "90000")
        self.assertEqual(str(salary["max"]), "100000")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the shared source helpers (inference, parsing, payload building).

The helpers are private by convention but are the shared vocabulary every
connector depends on, so they are imported under the names the modules expose.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jobtracker.core.models import Candidate, ExistingRef, FetchMetrics
from jobtracker.sources.shared.infer import (
    _excerpt,
    _find_money_text,
    _infer_engagement_type,
    _infer_seniority,
    _infer_work_model,
    _matches_lane,
    _optional_iso,
)
from jobtracker.sources.shared.parse import (
    _first_link_text_from_html,
    _parse_json_ld_jobs,
    _soup,
    _text_from_html,
)
from jobtracker.sources.shared.payload import (
    DEFAULT_OUTPUT_DIR,
    _build_payload,
    _is_duplicate,
    _json,
    _load_existing_refs,
    _needs_detail,
    _payload_path,
    _write_payload,
)

LANE = {"include_terms": ["ios", "swiftui"], "exclude_terms": ["android", "react native"]}


class OptionalIsoTests(unittest.TestCase):
    def test_parses_rfc_822_dates(self) -> None:
        self.assertEqual(_optional_iso("Tue, 21 Apr 2026 09:00:00 +0000"), "2026-04-21T09:00:00+00:00")

    def test_passes_through_datetime_objects(self) -> None:
        moment = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(_optional_iso(moment), moment.isoformat())

    def test_blank_and_unparsable_values_are_none(self) -> None:
        self.assertIsNone(_optional_iso(None))
        self.assertIsNone(_optional_iso("   "))
        self.assertIsNone(_optional_iso("not a date at all"))


class ExcerptTests(unittest.TestCase):
    def test_collapses_whitespace(self) -> None:
        self.assertEqual(_excerpt("  Ship   the\niPhone app  "), "Ship the iPhone app")

    def test_returns_none_for_empty_input(self) -> None:
        self.assertIsNone(_excerpt(None))
        self.assertIsNone(_excerpt("  \n "))

    def test_truncates_with_ellipsis_at_limit(self) -> None:
        result = _excerpt("a" * 400)
        self.assertEqual(len(result), 280)
        self.assertTrue(result.endswith("…"))

    def test_honours_custom_limit(self) -> None:
        self.assertEqual(_excerpt("abcdefghij", limit=5), "abcd…")


class MoneyTextTests(unittest.TestCase):
    def test_finds_currency_ranges(self) -> None:
        self.assertEqual(_find_money_text("Salary: $4,000 - $6,000 per month"), "$4,000 - $6,000")

    def test_finds_iso_currency_codes(self) -> None:
        self.assertEqual(_find_money_text("Budget EUR 5000 monthly"), "EUR 5000")

    def test_returns_none_when_no_money_present(self) -> None:
        self.assertIsNone(_find_money_text("Competitive compensation"))
        self.assertIsNone(_find_money_text(None))


class InferWorkModelTests(unittest.TestCase):
    def test_hybrid_wins_over_remote(self) -> None:
        self.assertEqual(_infer_work_model("Hybrid — Berlin", "remote friendly"), "Hybrid")

    def test_detects_remote_synonyms(self) -> None:
        self.assertEqual(_infer_work_model("Telecommute"), "Remote")
        self.assertEqual(_infer_work_model(None, "Робота віддалено"), "Remote")

    def test_detects_onsite(self) -> None:
        self.assertEqual(_infer_work_model("Berlin office"), "On-site")

    def test_returns_none_without_signal(self) -> None:
        self.assertIsNone(_infer_work_model(None, None))
        self.assertIsNone(_infer_work_model("Berlin, Germany"))


class InferEngagementTypeTests(unittest.TestCase):
    def test_full_and_part_time(self) -> None:
        self.assertEqual(_infer_engagement_type("Full-time"), "Full-time")
        self.assertEqual(_infer_engagement_type("Part time role"), "Part-time")

    def test_contract_and_freelance_collapse_to_contract(self) -> None:
        self.assertEqual(_infer_engagement_type("Contract"), "Contract")
        self.assertEqual(_infer_engagement_type("Freelance project"), "Contract")

    def test_returns_none_without_signal(self) -> None:
        self.assertIsNone(_infer_engagement_type(""))
        self.assertIsNone(_infer_engagement_type("Engineering"))


class InferSeniorityTests(unittest.TestCase):
    def test_recognised_levels(self) -> None:
        cases = {
            "iOS Team Lead": "Lead",
            "Lead iOS Engineer": "Lead",
            "Principal iOS Engineer": "Principal",
            "Staff iOS Engineer": "Staff",
            "Senior iOS Engineer": "Senior",
            "Sr. iOS Engineer": "Senior",
            "Junior iOS Engineer": "Junior",
            "Middle iOS Engineer": "Mid",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(_infer_seniority(title), expected)

    def test_unlabelled_titles_are_none(self) -> None:
        self.assertIsNone(_infer_seniority("iOS Engineer"))
        self.assertIsNone(_infer_seniority(None))


class MatchesLaneTests(unittest.TestCase):
    def test_include_term_matches_case_insensitively(self) -> None:
        self.assertTrue(_matches_lane("Senior iOS Engineer", LANE))
        self.assertTrue(_matches_lane("SwiftUI specialist", LANE))

    def test_exclude_term_wins_over_include(self) -> None:
        self.assertFalse(_matches_lane("iOS and Android Engineer", LANE))
        self.assertFalse(_matches_lane("React Native / iOS Engineer", LANE))

    def test_titles_without_include_terms_do_not_match(self) -> None:
        self.assertFalse(_matches_lane("Backend Engineer", LANE))

    def test_empty_title_or_lane_never_matches(self) -> None:
        self.assertFalse(_matches_lane("", LANE))
        self.assertFalse(_matches_lane(None, LANE))
        self.assertFalse(_matches_lane("Senior iOS Engineer", {}))


class TextFromHtmlTests(unittest.TestCase):
    def test_strips_tags_and_collapses_whitespace(self) -> None:
        self.assertEqual(_text_from_html("<p>Ship the <b>iPhone</b>\n app.</p>"), "Ship the iPhone app.")

    def test_empty_input_returns_empty_string(self) -> None:
        self.assertEqual(_text_from_html(None), "")

    def test_soup_parses_markup(self) -> None:
        soup = _soup('<a class="job" href="/x">Role</a>')
        self.assertEqual(soup.select_one("a.job").get("href"), "/x")


class ParseJsonLdJobsTests(unittest.TestCase):
    def test_collects_job_postings_from_objects_and_arrays(self) -> None:
        html = """
        <script type="application/ld+json">{"@type": "JobPosting", "title": "A"}</script>
        <script type="application/ld+json">[{"@type": "JobPosting", "title": "B"}, {"@type": "Organization"}]</script>
        """
        jobs = _parse_json_ld_jobs(html)
        self.assertEqual([job["title"] for job in jobs], ["A", "B"])

    def test_invalid_and_empty_blocks_are_skipped(self) -> None:
        html = """
        <script type="application/ld+json">{ not json }</script>
        <script type="application/ld+json"></script>
        <script type="application/json">{"@type": "JobPosting", "title": "Wrong media type"}</script>
        """
        self.assertEqual(_parse_json_ld_jobs(html), [])


class FirstLinkTextTests(unittest.TestCase):
    def test_returns_first_meaningful_anchor(self) -> None:
        html = '<a href="/companies/acme/">Acme Corp</a> — <a href="#reply">Apply</a>'
        self.assertEqual(_first_link_text_from_html(html), "Acme Corp")

    def test_skips_apply_anchors(self) -> None:
        html = '<a href="/jobs/1#reply">Відгукнутися</a><a href="/companies/acme/">Acme Corp</a>'
        self.assertEqual(_first_link_text_from_html(html), "Acme Corp")

    def test_returns_none_without_anchors(self) -> None:
        self.assertIsNone(_first_link_text_from_html("<p>No links</p>"))
        self.assertIsNone(_first_link_text_from_html(None))


def _candidate(external_id: str = "job-1", source_url: str = "https://jobs.example.com/1") -> Candidate:
    return Candidate(
        external_id=external_id,
        title="Senior iOS Engineer",
        source_url=source_url,
        apply_url=source_url,
        company="Acme Corp",
        summary="Ship the iPhone app.",
        first_seen_at="2026-04-20T09:00:00+00:00",
        last_seen_at="2026-04-21T09:00:00+00:00",
        metadata={"provider": "acme"},
    )


class ExistingRefHelperTests(unittest.TestCase):
    def test_load_existing_refs_short_circuits_without_connection(self) -> None:
        self.assertEqual(_load_existing_refs(None, "acme", [_candidate()]), ({}, {}))

    def test_load_existing_refs_short_circuits_without_candidates(self) -> None:
        self.assertEqual(_load_existing_refs(object(), "acme", []), ({}, {}))

    def test_is_duplicate_matches_on_either_key(self) -> None:
        candidate = _candidate()
        by_external_id = {"job-1": ExistingRef("job-1", None, None)}
        by_source_url = {"https://jobs.example.com/1": ExistingRef(None, "https://jobs.example.com/1", None)}

        self.assertTrue(_is_duplicate(candidate, by_external_id, {}))
        self.assertTrue(_is_duplicate(candidate, {}, by_source_url))
        self.assertFalse(_is_duplicate(candidate, {}, {}))

    def test_needs_detail_is_true_for_unseen_candidates(self) -> None:
        self.assertTrue(_needs_detail(_candidate(), "acme", {}, {}))

    def test_needs_detail_is_false_for_known_non_dou_candidates(self) -> None:
        refs = {"job-1": ExistingRef("job-1", None, datetime(2026, 4, 1, tzinfo=timezone.utc))}
        self.assertFalse(_needs_detail(_candidate(), "acme", refs, {}))

    def test_needs_detail_refreshes_dou_candidates_seen_again(self) -> None:
        stale = {"job-1": ExistingRef("job-1", None, datetime(2026, 4, 1, tzinfo=timezone.utc))}
        fresh = {"job-1": ExistingRef("job-1", None, datetime(2026, 5, 1, tzinfo=timezone.utc))}

        self.assertTrue(_needs_detail(_candidate(), "dou", stale, {}))
        self.assertFalse(_needs_detail(_candidate(), "dou", fresh, {}))


class BuildPayloadTests(unittest.TestCase):
    def build(self, *, blockers: list[str] | None = None) -> dict:
        started = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 4, 21, 9, 1, tzinfo=timezone.utc)
        metrics = FetchMetrics()
        metrics.jobs_discovered = 1
        metrics.jobs_emitted = 1
        return _build_payload(
            "acme",
            "acme-2026-04-21",
            started,
            finished,
            "completed",
            "acme discovered 1 job",
            blockers or [],
            metrics,
            [_candidate()],
        )

    def test_payload_shape_matches_the_automation_contract(self) -> None:
        payload = self.build()

        self.assertEqual(payload["run"]["run_key"], "acme-2026-04-21")
        self.assertEqual(payload["run"]["status"], "completed")
        self.assertEqual(payload["run"]["source_items_count"], 1)
        self.assertEqual(payload["run"]["opportunities_count"], 1)
        self.assertEqual(payload["run"]["manual_review_count"], 0)
        self.assertEqual(payload["run"]["metrics"]["run_status"], "completed")
        self.assertEqual(payload["source_items"][0]["external_id"], "acme:job-1")
        self.assertEqual(payload["opportunities"][0]["external_id"], "job-1")
        self.assertEqual(payload["opportunities"][0]["source_items"], ["acme:job-1"])
        self.assertEqual(payload["manual_review_blockers"], [])

    def test_blockers_are_recorded_for_manual_review(self) -> None:
        payload = self.build(blockers=["listing page timed out"])

        self.assertEqual(payload["run"]["manual_review_count"], 1)
        self.assertEqual(payload["manual_review_blockers"], [{"reason": "listing page timed out"}])

    def test_json_helper_is_readable_and_unicode_safe(self) -> None:
        rendered = _json({"title": "Розробник iOS"})
        self.assertIn("Розробник iOS", rendered)
        self.assertEqual(json.loads(rendered)["title"], "Розробник iOS")


class PayloadPathTests(unittest.TestCase):
    def test_explicit_path_wins(self) -> None:
        self.assertEqual(_payload_path("acme", "run-1", "/tmp/out.json"), Path("/tmp/out.json"))

    def test_default_path_is_derived_from_provider_and_run_key(self) -> None:
        self.assertEqual(_payload_path("acme", "run-1", None), DEFAULT_OUTPUT_DIR / "acme-run-1.payload.json")

    def test_write_payload_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "deeper" / "out.payload.json"

            written = _write_payload(target, {"summary": "ok"})

            self.assertEqual(written, target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"summary": "ok"})

    def test_write_payload_is_a_no_op_without_a_path(self) -> None:
        self.assertIsNone(_write_payload(None, {"summary": "ok"}))


if __name__ == "__main__":
    unittest.main()

"""Tests for the core dataclasses and error types shared by every connector."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.core.errors import (
    ConnectorHealthError,
    MissingConfigurationError,
    UnknownConnectorError,
)
from jobtracker.core.models import (
    Candidate,
    CollectionContext,
    CollectionResult,
    ExistingRef,
    FetchMetrics,
)


def build_candidate(**overrides) -> Candidate:
    fields = {
        "external_id": "job-1",
        "title": "Senior iOS Engineer",
        "source_url": "https://jobs.example.com/1",
        "apply_url": "https://jobs.example.com/1/apply",
        "company": "Acme Corp",
        "location": "Remote — EMEA",
        "work_model": "Remote",
        "engagement_type": "Full-time",
        "seniority": "Senior",
        "compensation_text": "$8,000 - $10,000",
        "summary": "Ship the iPhone app.",
        "description": "Ship the iPhone app. Own the SwiftUI checkout flow.",
        "first_seen_at": "2026-04-20T09:00:00+00:00",
        "last_seen_at": "2026-04-21T09:00:00+00:00",
        "metadata": {"provider": "acme", "board_token": "acme"},
    }
    fields.update(overrides)
    return Candidate(**fields)


class CandidateTests(unittest.TestCase):
    def test_source_item_id_is_provider_scoped(self) -> None:
        self.assertEqual(build_candidate().source_item_id("acme"), "acme:job-1")

    def test_as_source_item_shape(self) -> None:
        item = build_candidate().as_source_item("acme")

        self.assertEqual(item["source_type"], "job_posting")
        self.assertEqual(item["external_id"], "acme:job-1")
        self.assertEqual(item["source_url"], "https://jobs.example.com/1")
        self.assertEqual(item["timestamp"], "2026-04-21T09:00:00+00:00")
        self.assertEqual(item["title"], "Senior iOS Engineer")
        self.assertEqual(item["summary"], "Ship the iPhone app.")
        self.assertEqual(item["raw_text"], "Ship the iPhone app. Own the SwiftUI checkout flow.")
        self.assertEqual(item["provider_metadata"], {"provider": "acme", "board_token": "acme"})

    def test_as_source_item_falls_back_to_first_seen_at(self) -> None:
        item = build_candidate(last_seen_at=None).as_source_item("acme")

        self.assertEqual(item["timestamp"], "2026-04-20T09:00:00+00:00")

    def test_as_opportunity_shape(self) -> None:
        opportunity = build_candidate().as_opportunity("acme")

        self.assertEqual(opportunity["opportunity_type"], "employment")
        self.assertEqual(opportunity["external_id"], "job-1")
        self.assertEqual(opportunity["company"], "Acme Corp")
        self.assertEqual(opportunity["apply_url"], "https://jobs.example.com/1/apply")
        self.assertEqual(opportunity["work_model"], "Remote")
        self.assertEqual(opportunity["engagement_type"], "Full-time")
        self.assertEqual(opportunity["seniority"], "Senior")
        self.assertEqual(opportunity["compensation_text"], "$8,000 - $10,000")
        self.assertEqual(opportunity["source_status"], "discovered")
        self.assertEqual(opportunity["source_items"], ["acme:job-1"])
        self.assertEqual(opportunity["first_seen_at"], "2026-04-20T09:00:00+00:00")

    def test_optional_fields_default_to_none_and_empty_metadata(self) -> None:
        candidate = Candidate(
            external_id="job-2",
            title="iOS Engineer",
            source_url="https://jobs.example.com/2",
            apply_url="https://jobs.example.com/2",
        )

        self.assertIsNone(candidate.company)
        self.assertEqual(candidate.metadata, {})
        self.assertIsNone(candidate.as_source_item("acme")["timestamp"])

    def test_candidates_are_frozen(self) -> None:
        with self.assertRaises(Exception):
            build_candidate().title = "Something else"


class FetchMetricsTests(unittest.TestCase):
    def test_defaults_start_at_zero(self) -> None:
        metrics = FetchMetrics()

        self.assertEqual(metrics.request_count, 0)
        self.assertEqual(metrics.board_tokens, [])
        self.assertEqual(metrics.partial_blockers, [])

    def test_record_request_routes_by_kind(self) -> None:
        metrics = FetchMetrics()

        metrics.record_request("list", 120)
        metrics.record_request("detail", 250)
        metrics.record_request("api", 90)

        self.assertEqual(metrics.request_count, 3)
        self.assertEqual(metrics.list_request_count, 1)
        self.assertEqual(metrics.list_latency_ms, 120)
        self.assertEqual(metrics.detail_request_count, 1)
        self.assertEqual(metrics.detail_latency_ms, 250)
        self.assertEqual(metrics.api_request_count, 1)
        self.assertEqual(metrics.api_latency_ms, 90)
        self.assertEqual(metrics.retry_count, 0)

    def test_unknown_kinds_count_as_list_requests(self) -> None:
        metrics = FetchMetrics()

        metrics.record_request("something-else", 10)

        self.assertEqual(metrics.list_request_count, 1)
        self.assertEqual(metrics.list_latency_ms, 10)

    def test_retries_are_counted_separately(self) -> None:
        metrics = FetchMetrics()

        metrics.record_request("list", 100)
        metrics.record_request("list", 150, retried=True)

        self.assertEqual(metrics.request_count, 2)
        self.assertEqual(metrics.retry_count, 1)
        self.assertEqual(metrics.list_latency_ms, 250)

    def test_to_dict_includes_the_run_status(self) -> None:
        metrics = FetchMetrics()
        metrics.record_request("api", 40)
        metrics.jobs_discovered = 5
        metrics.jobs_emitted = 3
        metrics.jobs_skipped_as_duplicates = 1
        metrics.jobs_skipped_by_filter = 1
        metrics.board_tokens = ["acme"]
        metrics.partial_blockers = ["board other failed"]

        payload = metrics.to_dict("partial")

        self.assertEqual(payload["run_status"], "partial")
        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["api_latency_ms"], 40)
        self.assertEqual(payload["jobs_discovered"], 5)
        self.assertEqual(payload["jobs_emitted"], 3)
        self.assertEqual(payload["jobs_skipped_as_duplicates"], 1)
        self.assertEqual(payload["jobs_skipped_by_filter"], 1)
        self.assertEqual(payload["board_tokens"], ["acme"])
        self.assertEqual(payload["partial_blockers"], ["board other failed"])


class CollectionContextTests(unittest.TestCase):
    def test_role_lane_and_provider_config_read_from_targets(self) -> None:
        ctx = CollectionContext(
            targets={
                "role_lane": {"name": "iOS/macOS", "include_terms": ["ios"]},
                "providers": {"acme": {"listing_url": "https://jobs.example.com"}},
            },
            provider_slug="acme",
        )

        self.assertEqual(ctx.role_lane["name"], "iOS/macOS")
        self.assertEqual(ctx.provider_config["listing_url"], "https://jobs.example.com")

    def test_missing_targets_degrade_to_empty_mappings(self) -> None:
        ctx = CollectionContext(provider_slug="acme")

        self.assertEqual(ctx.role_lane, {})
        self.assertEqual(ctx.provider_config, {})
        self.assertIsNone(ctx.conn)
        self.assertIsInstance(ctx.metrics, FetchMetrics)


class CollectionResultTests(unittest.TestCase):
    def build(self, **overrides) -> CollectionResult:
        candidate = build_candidate()
        fields = {
            "provider_slug": "acme",
            "candidates": [candidate],
            "status": "completed",
            "summary": "acme discovered 1 job",
            "blockers": [],
            "metrics": FetchMetrics(),
            "run_key": "acme-2026-04-21",
            "payload": {"source_items": [candidate.as_source_item("acme")]},
            "payload_path": Path("outputs/acme.payload.json"),
        }
        fields.update(overrides)
        return CollectionResult(**fields)

    def test_to_dict_summarizes_a_dry_run(self) -> None:
        payload = self.build().to_dict(dry_run=True)

        self.assertEqual(payload["provider"], "acme")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["run_key"], "acme-2026-04-21")
        self.assertEqual(payload["payload_path"], "outputs/acme.payload.json")
        self.assertEqual(payload["opportunities"], 1)
        self.assertEqual(payload["source_items"], 1)
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["metrics"]["run_status"], "completed")
        self.assertFalse(payload["persisted"])
        self.assertIsNone(payload["persisted_result"])

    def test_missing_payload_path_serializes_to_none(self) -> None:
        self.assertIsNone(self.build(payload_path=None).to_dict(dry_run=True)["payload_path"])

    def test_persisted_runs_carry_the_store_result(self) -> None:
        payload = self.build(
            persisted=True,
            persisted_result={"run_key": "acme-2026-04-21", "opportunities": 1},
        ).to_dict(dry_run=False)

        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["persisted"])
        self.assertEqual(payload["persisted_result"]["opportunities"], 1)

    def test_status_flows_into_the_metrics_block(self) -> None:
        payload = self.build(status="partial", blockers=["listing timed out"]).to_dict(dry_run=True)

        self.assertEqual(payload["metrics"]["run_status"], "partial")
        self.assertEqual(payload["blockers"], ["listing timed out"])

    def test_payload_without_source_items_counts_zero(self) -> None:
        self.assertEqual(self.build(payload={}).to_dict(dry_run=True)["source_items"], 0)


class ExistingRefTests(unittest.TestCase):
    def test_holds_the_dedupe_keys(self) -> None:
        seen_at = datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc)
        ref = ExistingRef("job-1", "https://jobs.example.com/1", seen_at)

        self.assertEqual(ref.external_id, "job-1")
        self.assertEqual(ref.last_seen_at, seen_at)


class ErrorTests(unittest.TestCase):
    def test_unknown_connector_error_is_a_lookup_error(self) -> None:
        error = UnknownConnectorError("Unknown source 'nope'. Available: acme")

        self.assertIsInstance(error, LookupError)
        self.assertIn("Available: acme", str(error))
        with self.assertRaises(LookupError):
            raise error

    def test_connector_health_error_is_a_runtime_error(self) -> None:
        self.assertIsInstance(ConnectorHealthError("listing unreachable"), RuntimeError)

    def test_missing_configuration_error_is_re_exported_from_db(self) -> None:
        from jobtracker.db import MissingConfigurationError as DbMissingConfigurationError

        self.assertIs(MissingConfigurationError, DbMissingConfigurationError)
        self.assertIsInstance(MissingConfigurationError("JOBTRACKER_DATABASE_URL is required"), RuntimeError)


if __name__ == "__main__":
    unittest.main()

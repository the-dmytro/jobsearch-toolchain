"""Connector contract tests — every registered connector must satisfy basic invariants."""

from __future__ import annotations

import unittest
from pathlib import Path

from jobtracker.core.models import CollectionContext, FetchMetrics
from jobtracker.sources.registry import resolve_source, source_registry
from jobtracker.store.generic.memory import MemoryJobStore


class ConnectorContractTests(unittest.TestCase):
    def test_all_sources_have_slug_and_health(self) -> None:
        from jobtracker.sources import services  # noqa: F401 — trigger registration

        for slug in source_registry.all():
            source = resolve_source(slug, root=Path.cwd())
            self.assertTrue(source.slug, f"{slug} missing slug")
            ctx = _minimal_collection_ctx(slug)
            report = source.health(ctx)
            self.assertIsInstance(report, list)

    def test_memory_store_roundtrip(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        store = MemoryJobStore()
        payload = {
            "run": {
                "run_key": "test-run-1",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "status": "success",
                "summary": "test",
                "report_email_sent": False,
                "source_items_count": 1,
                "opportunities_count": 1,
                "evaluations_count": 0,
                "manual_review_count": 0,
            },
            "source_items": [
                {
                    "source_type": "job_posting",
                    "external_id": "test:job-1",
                    "source_url": "https://example.com/jobs/1",
                    "title": "Test Job",
                }
            ],
            "opportunities": [
                {
                    "opportunity_type": "employment",
                    "external_id": "job-1",
                    "title": "Test Job",
                    "source_url": "https://example.com/jobs/1",
                    "apply_url": "https://example.com/jobs/1",
                    "source_items": ["test:job-1"],
                }
            ],
            "manual_review_blockers": [],
            "summary": "test",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            result = store.upsert_run_payload("test", path)
            self.assertEqual(result.run_key, "test-run-1")
            dupes = store.check_duplicates("test", None, None, external_id="job-1")
            self.assertIsInstance(dupes, list)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_config_only_jsonld_kind_registered(self) -> None:
        from jobtracker.sources.generic.jsonld import JsonLdSource

        self.assertEqual(JsonLdSource.slug, "jsonld")


def _minimal_collection_ctx(slug: str) -> CollectionContext:
    from jobtracker.sources.shared.fetch import FixtureFetcher

    metrics = FetchMetrics()
    return CollectionContext(
        conn=None,
        fetcher=FixtureFetcher(None, metrics),
        targets={"role_lane": {"name": "test", "include_terms": ["engineer"], "exclude_terms": []}},
        metrics=metrics,
        provider_slug=slug,
        options={"listing_url": "https://example.com"},
    )


if __name__ == "__main__":
    unittest.main()

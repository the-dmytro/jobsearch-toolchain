"""Discovery tests for the config-only generic source bases.

Each generic base is driven through ``discover`` with a throwaway fetcher that
serves files written into a per-test temporary directory, so the tests exercise
the real parsing/filtering code without touching the network.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from jobtracker.core.models import CollectionContext, FetchMetrics
from jobtracker.sources.generic.csv import CsvSource
from jobtracker.sources.generic.html import HtmlSource
from jobtracker.sources.generic.json_api import JsonApiSource
from jobtracker.sources.generic.jsonld import JsonLdSource
from jobtracker.sources.generic.rss import RssSource
from jobtracker.sources.generic.sitemap import SitemapSource

ROLE_LANE = {
    "name": "iOS/macOS",
    "include_terms": ["ios", "swiftui", "iphone", "engineer"],
    "exclude_terms": ["android", "designer"],
}


class FileFetcher:
    """Minimal ``Fetcher`` that resolves URLs against files on disk."""

    def __init__(self, metrics: FetchMetrics, routes: dict[str, Path]) -> None:
        self._metrics = metrics
        self._routes = dict(routes)
        self.requested: list[tuple[str, str]] = []
        self.closed = False

    def get_text(self, url: str, kind: str) -> str:
        self.requested.append((url, kind))
        self._metrics.record_request(kind, 1)
        try:
            return self._routes[url].read_text(encoding="utf-8")
        except KeyError as exc:
            raise FileNotFoundError(f"no fixture routed for {url}") from exc

    def get_json(self, url: str, kind: str) -> Any:
        return json.loads(self.get_text(url, kind))

    def close(self) -> None:
        self.closed = True


class GenericSourceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.metrics = FetchMetrics()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def context(
        self,
        *,
        routes: dict[str, Path],
        options: dict[str, Any],
        slug: str = "acme",
        lane: dict[str, Any] | None = None,
        conn: Any | None = None,
    ) -> CollectionContext:
        fetcher = FileFetcher(self.metrics, routes)
        self.fetcher = fetcher
        return CollectionContext(
            conn=conn,
            fetcher=fetcher,
            targets={"role_lane": ROLE_LANE if lane is None else lane},
            metrics=self.metrics,
            provider_slug=slug,
            options=options,
        )


class RssSourceTests(GenericSourceTestCase):
    FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Acme jobs</title>
    <item>
      <title>Senior iOS Engineer</title>
      <link>https://jobs.example.com/vacancies/ios-101/</link>
      <description>&lt;a href="https://jobs.example.com/companies/acme/"&gt;Acme Corp&lt;/a&gt; is hiring for SwiftUI work.</description>
      <pubDate>Tue, 21 Apr 2026 09:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Middle Android Developer</title>
      <link>https://jobs.example.com/vacancies/android-202/</link>
      <description>Kotlin role.</description>
      <pubDate>Tue, 21 Apr 2026 09:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""

    def test_discover_emits_matching_items_only(self) -> None:
        url = "https://jobs.example.com/feed.xml"
        ctx = self.context(
            routes={url: self.write("feed.xml", self.FEED)},
            options={"feed_url": url},
        )

        candidates, status, blockers = RssSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual([candidate.title for candidate in candidates], ["Senior iOS Engineer"])
        candidate = candidates[0]
        self.assertEqual(candidate.source_url, "https://jobs.example.com/vacancies/ios-101/")
        self.assertEqual(candidate.apply_url, candidate.source_url)
        self.assertEqual(candidate.company, "Acme Corp")
        self.assertEqual(candidate.seniority, "Senior")
        self.assertIn("SwiftUI", candidate.summary)
        self.assertEqual(candidate.metadata["provider"], "rss")
        self.assertEqual(self.metrics.jobs_discovered, 1)
        self.assertEqual(self.metrics.jobs_emitted, 1)
        self.assertEqual(self.metrics.jobs_skipped_by_filter, 1)

    def test_discover_supports_multiple_feed_urls(self) -> None:
        first = "https://jobs.example.com/feed-a.xml"
        second = "https://jobs.example.com/feed-b.xml"
        ctx = self.context(
            routes={
                first: self.write("feed-a.xml", self.FEED),
                second: self.write("feed-b.xml", self.FEED),
            },
            options={"feed_urls": [first, second]},
        )

        candidates, status, _blockers = RssSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(len(candidates), 2)

    def test_unreachable_feed_is_reported_as_partial(self) -> None:
        ctx = self.context(routes={}, options={"feed_url": "https://jobs.example.com/missing.xml"})

        candidates, status, blockers = RssSource().discover(ctx)

        self.assertEqual(candidates, [])
        self.assertEqual(status, "partial")
        self.assertEqual(len(blockers), 1)
        self.assertIn("RSS fetch failed", blockers[0])


class JsonLdSourceTests(GenericSourceTestCase):
    @property
    def listing_html(self) -> str:
        fixture = Path(__file__).resolve().parent / "fixtures" / "jsonld_listing.html"
        return fixture.read_text(encoding="utf-8")

    def test_discover_reads_job_posting_nodes(self) -> None:
        url = "https://careers.acme.example/jobs"
        ctx = self.context(
            routes={url: self.write("listing.html", self.listing_html)},
            options={"listing_url": url},
        )

        candidates, status, blockers = JsonLdSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.external_id, "acme-ios-101")
        self.assertEqual(candidate.title, "Senior iOS Engineer")
        self.assertEqual(candidate.company, "Acme Corp")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.engagement_type, "Full-time")
        self.assertEqual(candidate.seniority, "Senior")
        self.assertNotIn("utm_source", candidate.source_url)
        self.assertIn("SwiftUI", candidate.description)
        self.assertEqual(candidate.metadata["json_ld"]["identifier"], "acme-ios-101")

    def test_listing_without_job_postings_is_blocked(self) -> None:
        url = "https://careers.acme.example/empty"
        ctx = self.context(
            routes={url: self.write("empty.html", "<html><body>No structured data</body></html>")},
            options={"listing_url": url},
        )

        candidates, status, blockers = JsonLdSource().discover(ctx)

        self.assertEqual(candidates, [])
        self.assertEqual(status, "partial")
        self.assertIn("no JobPosting JSON-LD found", blockers[0])


class HtmlSourceTests(GenericSourceTestCase):
    LISTING = """
    <html><body>
      <ul class="jobs">
        <li><a class="job-link" href="/vacancies/ios-101/">Senior iOS Engineer</a></li>
        <li><a class="job-link" href="/vacancies/ios-101/">Senior iOS Engineer</a></li>
        <li><a class="job-link" href="/vacancies/android-202/">Android Developer</a></li>
        <li><a class="other-link" href="/about/">About iOS at Acme</a></li>
      </ul>
    </body></html>
    """

    def test_discover_follows_link_selector_and_dedupes_urls(self) -> None:
        url = "https://jobs.example.com/list"
        ctx = self.context(
            routes={url: self.write("list.html", self.LISTING)},
            options={
                "listing_url": url,
                "link_selector": "a.job-link",
                "base_url": "https://jobs.example.com/",
            },
        )

        candidates, status, blockers = HtmlSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(
            [candidate.source_url for candidate in candidates],
            ["https://jobs.example.com/vacancies/ios-101/"],
        )
        self.assertEqual(candidates[0].seniority, "Senior")
        self.assertEqual(candidates[0].metadata["provider"], "html")

    def test_relative_links_resolve_against_listing_url_without_base_url(self) -> None:
        url = "https://jobs.example.com/careers/list"
        ctx = self.context(
            routes={url: self.write("list.html", self.LISTING)},
            options={"listing_url": url, "link_selector": "a.job-link"},
        )

        candidates, _status, _blockers = HtmlSource().discover(ctx)

        self.assertEqual(candidates[0].source_url, "https://jobs.example.com/vacancies/ios-101/")


class JsonApiSourceTests(GenericSourceTestCase):
    PAYLOAD = {
        "jobs": [
            {
                "id": 991,
                "title": "Senior iOS Engineer",
                "absolute_url": "https://boards.example.com/acme/jobs/991",
                "location": {"name": "Remote"},
                "content": "<p>Ship the iPhone app.</p>",
                "updated_at": "2026-04-21T09:00:00+00:00",
            },
            {
                "id": 992,
                "title": "Product Designer",
                "absolute_url": "https://boards.example.com/acme/jobs/992",
                "location": {"name": "Berlin"},
                "content": "<p>Design work.</p>",
            },
            "not-a-dict",
        ]
    }

    def build_source(self) -> JsonApiSource:
        source = JsonApiSource()
        source.slug = "acme_api"
        source.api_url_template = "https://boards.example.com/api/{token}/jobs"
        source.jobs_key = "jobs"
        source.external_id_prefix = "acme:"
        return source

    def test_discover_expands_board_tokens(self) -> None:
        url = "https://boards.example.com/api/acme/jobs"
        ctx = self.context(
            routes={url: self.write("board.json", json.dumps(self.PAYLOAD))},
            options={"board_tokens": ["acme"]},
        )

        candidates, status, blockers = self.build_source().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.external_id, "acme:acme:991")
        self.assertEqual(candidate.location, "Remote")
        self.assertEqual(candidate.work_model, "Remote")
        self.assertEqual(candidate.description, "Ship the iPhone app.")
        self.assertEqual(candidate.metadata["board_token"], "acme")
        self.assertEqual(self.metrics.board_tokens, ["acme"])

    def test_max_boards_truncates_token_list(self) -> None:
        url = "https://boards.example.com/api/acme/jobs"
        ctx = self.context(
            routes={url: self.write("board.json", json.dumps(self.PAYLOAD))},
            options={"board_tokens": ["acme", "other"], "max_boards": 1},
        )

        _candidates, status, blockers = self.build_source().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(self.metrics.board_tokens, ["acme"])

    def test_top_level_list_payload_when_jobs_key_is_none(self) -> None:
        url = "https://boards.example.com/api/acme/jobs"
        source = self.build_source()
        source.jobs_key = None
        ctx = self.context(
            routes={url: self.write("board.json", json.dumps(self.PAYLOAD["jobs"][:1]))},
            options={"board_tokens": ["acme"]},
        )

        candidates, status, _blockers = source.discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(len(candidates), 1)

    def test_failing_board_becomes_partial_blocker(self) -> None:
        ctx = self.context(routes={}, options={"board_tokens": ["acme"]})

        candidates, status, blockers = self.build_source().discover(ctx)

        self.assertEqual(candidates, [])
        self.assertEqual(status, "partial")
        self.assertIn("acme_api board acme failed", blockers[0])
        self.assertEqual(self.metrics.partial_blockers, blockers)


class SitemapSourceTests(GenericSourceTestCase):
    SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://jobs.example.com/vacancy/senior-ios-engineer</loc></url>
  <url><loc>https://jobs.example.com/vacancy/android-developer</loc></url>
  <url><loc>https://jobs.example.com/about/ios-engineer-culture</loc></url>
</urlset>
"""

    def test_discover_derives_titles_from_url_slugs(self) -> None:
        url = "https://jobs.example.com/sitemap.xml"
        ctx = self.context(
            routes={url: self.write("sitemap.xml", self.SITEMAP)},
            options={"sitemap_url": url},
        )

        candidates, status, blockers = SitemapSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual(
            [candidate.title for candidate in candidates],
            ["senior ios engineer", "ios engineer culture"],
        )
        self.assertEqual(candidates[0].seniority, "Senior")

    def test_url_pattern_narrows_the_sitemap(self) -> None:
        url = "https://jobs.example.com/sitemap.xml"
        ctx = self.context(
            routes={url: self.write("sitemap.xml", self.SITEMAP)},
            options={"sitemap_url": url, "url_pattern": r"/vacancy/"},
        )

        candidates, _status, _blockers = SitemapSource().discover(ctx)

        self.assertEqual([candidate.title for candidate in candidates], ["senior ios engineer"])


class CsvSourceTests(GenericSourceTestCase):
    CSV = (
        "title,url,company\n"
        "Senior iOS Engineer,https://jobs.example.com/1,Acme Corp\n"
        "Android Developer,https://jobs.example.com/2,Acme Corp\n"
        "iOS Engineer without link,,Acme Corp\n"
    )

    def test_discover_reads_default_columns(self) -> None:
        url = "https://jobs.example.com/export.csv"
        ctx = self.context(
            routes={url: self.write("export.csv", self.CSV)},
            options={"csv_url": url},
        )

        candidates, status, blockers = CsvSource().discover(ctx)

        self.assertEqual(status, "completed")
        self.assertEqual(blockers, [])
        self.assertEqual([candidate.title for candidate in candidates], ["Senior iOS Engineer"])
        self.assertEqual(candidates[0].company, "Acme Corp")

    def test_custom_column_names(self) -> None:
        url = "https://jobs.example.com/export.csv"
        content = "role,link,employer\nSenior iOS Engineer,https://jobs.example.com/1,Acme Corp\n"
        ctx = self.context(
            routes={url: self.write("custom.csv", content)},
            options={
                "csv_url": url,
                "title_column": "role",
                "url_column": "link",
                "company_column": "employer",
            },
        )

        candidates, _status, _blockers = CsvSource().discover(ctx)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].company, "Acme Corp")


class GenericSourceContractTests(GenericSourceTestCase):
    def test_every_generic_source_reports_empty_health(self) -> None:
        ctx = self.context(routes={}, options={})
        for source in (RssSource(), JsonLdSource(), HtmlSource(), JsonApiSource(), SitemapSource(), CsvSource()):
            with self.subTest(source=source.slug):
                self.assertEqual(source.health(ctx), [])

    def test_sources_return_empty_results_without_configured_urls(self) -> None:
        for source in (RssSource(), JsonLdSource(), HtmlSource(), SitemapSource(), CsvSource()):
            with self.subTest(source=source.slug):
                ctx = self.context(routes={}, options={})
                candidates, status, blockers = source.discover(ctx)
                self.assertEqual(candidates, [])
                self.assertEqual(status, "completed")
                self.assertEqual(blockers, [])


if __name__ == "__main__":
    unittest.main()

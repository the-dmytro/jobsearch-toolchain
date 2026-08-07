from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.shared.infer import _infer_seniority, _matches_lane
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space


class SitemapSource:
    slug: str = "sitemap"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        sitemap_urls = opts.get("sitemap_urls") or [opts.get("sitemap_url")]
        url_pattern = opts.get("url_pattern")
        lane = ctx.role_lane
        metrics = ctx.metrics
        candidates: list[Candidate] = []
        blockers: list[str] = []
        pattern = re.compile(url_pattern) if url_pattern else None
        for sitemap_url in [url for url in sitemap_urls if url]:
            try:
                root = ET.fromstring(ctx.fetcher.get_text(sitemap_url, "list"))
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//sm:loc", ns) or root.findall(".//loc"):
                    source_url = clean_url(loc.text)
                    if not source_url:
                        continue
                    if pattern and not pattern.search(source_url):
                        continue
                    title = normalize_space(source_url.rsplit("/", 1)[-1].replace("-", " "))
                    if not _matches_lane(title, lane):
                        metrics.jobs_skipped_by_filter += 1
                        continue
                    candidates.append(
                        Candidate(
                            external_id=source_url,
                            title=title,
                            source_url=source_url,
                            apply_url=source_url,
                            seniority=_infer_seniority(title),
                            metadata={"provider": self.slug},
                        )
                    )
            except Exception as exc:
                blockers.append(f"Sitemap fetch failed for {sitemap_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        metrics.jobs_emitted = len(candidates)
        status = "partial" if blockers else "completed"
        return candidates, status, blockers

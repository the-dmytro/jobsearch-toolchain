from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.shared.infer import _excerpt, _infer_seniority, _matches_lane, _optional_iso
from jobtracker.sources.shared.parse import _first_link_text_from_html, _text_from_html
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space


class RssSource:
    slug: str = "rss"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        feed_urls = opts.get("feed_urls") or [opts.get("feed_url")]
        lane = ctx.role_lane
        metrics = ctx.metrics
        candidates: list[Candidate] = []
        blockers: list[str] = []
        for feed_url in [url for url in feed_urls if url]:
            try:
                root = ET.fromstring(ctx.fetcher.get_text(feed_url, "list"))
                for item in root.findall(".//item"):
                    title = normalize_space(item.findtext("title"))
                    if not _matches_lane(title, lane):
                        metrics.jobs_skipped_by_filter += 1
                        continue
                    source_url = clean_url(item.findtext("link"))
                    if not source_url:
                        continue
                    description_html = item.findtext("description")
                    published_at = _optional_iso(item.findtext("pubDate"))
                    candidates.append(
                        Candidate(
                            external_id=source_url,
                            title=title,
                            source_url=source_url,
                            apply_url=source_url,
                            company=_first_link_text_from_html(description_html),
                            seniority=_infer_seniority(title),
                            summary=_excerpt(_text_from_html(description_html)),
                            first_seen_at=published_at,
                            last_seen_at=published_at,
                            metadata={"provider": self.slug},
                        )
                    )
            except Exception as exc:
                blockers.append(f"RSS fetch failed for {feed_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        metrics.jobs_emitted = len(candidates)
        status = "partial" if blockers else "completed"
        return candidates, status, blockers

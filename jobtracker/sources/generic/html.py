from __future__ import annotations

from urllib.parse import urljoin

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.shared.infer import _excerpt, _infer_seniority, _matches_lane
from jobtracker.sources.shared.parse import _soup
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space


class HtmlSource:
    slug: str = "html"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        listing_urls = opts.get("listing_urls") or [opts.get("listing_url")]
        base_url = opts.get("base_url") or ""
        link_selector = opts.get("link_selector") or "a[href]"
        lane = ctx.role_lane
        metrics = ctx.metrics
        candidates: list[Candidate] = []
        blockers: list[str] = []
        seen: set[str] = set()
        for listing_url in [url for url in listing_urls if url]:
            try:
                soup = _soup(ctx.fetcher.get_text(listing_url, "list"))
                for anchor in soup.select(link_selector):
                    href = anchor.get("href")
                    if not href:
                        continue
                    title = normalize_space(anchor.get_text(" ", strip=True))
                    if not title or not _matches_lane(title, lane):
                        if title:
                            metrics.jobs_skipped_by_filter += 1
                        continue
                    source_url = clean_url(urljoin(base_url or listing_url, href))
                    if not source_url or source_url in seen:
                        continue
                    seen.add(source_url)
                    candidates.append(
                        Candidate(
                            external_id=source_url,
                            title=title,
                            source_url=source_url,
                            apply_url=source_url,
                            seniority=_infer_seniority(title),
                            summary=_excerpt(title),
                            metadata={"provider": self.slug},
                        )
                    )
            except Exception as exc:
                blockers.append(f"HTML listing fetch failed for {listing_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        metrics.jobs_emitted = len(candidates)
        status = "partial" if blockers else "completed"
        return candidates, status, blockers

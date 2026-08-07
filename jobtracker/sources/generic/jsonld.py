from __future__ import annotations

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.shared.infer import (
    _excerpt,
    _infer_engagement_type,
    _infer_seniority,
    _infer_work_model,
    _matches_lane,
    _optional_iso,
)
from jobtracker.sources.shared.parse import _parse_json_ld_jobs, _text_from_html
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space


class JsonLdSource:
    slug: str = "jsonld"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        listing_urls = opts.get("listing_urls") or [opts.get("listing_url")]
        lane = ctx.role_lane
        metrics = ctx.metrics
        candidates: list[Candidate] = []
        blockers: list[str] = []
        for listing_url in [url for url in listing_urls if url]:
            try:
                jobs = _parse_json_ld_jobs(ctx.fetcher.get_text(listing_url, "list"))
                if not jobs:
                    blockers.append(f"{listing_url}: no JobPosting JSON-LD found.")
                    continue
                for item in jobs:
                    title = normalize_space(item.get("title"))
                    if not _matches_lane(title, lane):
                        metrics.jobs_skipped_by_filter += 1
                        continue
                    source_url = clean_url(item.get("url"))
                    if not source_url:
                        continue
                    description = _text_from_html(item.get("description"))
                    candidates.append(
                        Candidate(
                            external_id=str(item.get("identifier") or source_url),
                            title=title,
                            source_url=source_url,
                            apply_url=source_url,
                            company=normalize_space(((item.get("hiringOrganization") or {}).get("name"))) or None,
                            work_model=_infer_work_model(item.get("jobLocationType"), description),
                            engagement_type=_infer_engagement_type(item.get("employmentType"), description),
                            seniority=_infer_seniority(title),
                            summary=_excerpt(description),
                            description=description or None,
                            first_seen_at=_optional_iso(item.get("datePosted")),
                            last_seen_at=_optional_iso(item.get("validThrough")) or _optional_iso(item.get("datePosted")),
                            metadata={"provider": self.slug, "json_ld": item},
                        )
                    )
            except Exception as exc:
                blockers.append(f"JSON-LD fetch failed for {listing_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        metrics.jobs_emitted = len(candidates)
        status = "partial" if blockers else "completed"
        return candidates, status, blockers

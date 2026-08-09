from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.registry import register_source
from jobtracker.sources.shared.infer import (
    _excerpt,
    _find_money_text,
    _infer_engagement_type,
    _infer_seniority,
    _infer_work_model,
    _matches_lane,
    _optional_iso,
)
from jobtracker.sources.shared.parse import _parse_json_ld_jobs, _soup, _text_from_html
from jobtracker.sources.shared.payload import _is_duplicate, _load_existing_refs
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space

_DJINNI_JOB_RE = re.compile(r"/jobs/(\d+)(?:-[^/?#]+)?/?$")


def _djinni_external_id(url: str | None, identifier: str | None = None) -> str | None:
    if normalize_space(identifier):
        return normalize_space(identifier)
    cleaned = clean_url(url)
    if not cleaned:
        return None
    match = _DJINNI_JOB_RE.search(urlparse(cleaned).path)
    return match.group(1) if match else None


def _parse_djinni_listing(
    listing_html: str, lane: dict[str, Any], metrics: Any
) -> tuple[list[Candidate], str | None]:
    jobs = _parse_json_ld_jobs(listing_html)
    if not jobs:
        return [], "Djinni listing did not expose JobPosting JSON-LD."
    candidates: list[Candidate] = []
    for item in jobs:
        title = normalize_space(item.get("title"))
        if not _matches_lane(title, lane):
            metrics.jobs_skipped_by_filter += 1
            continue
        source_url = clean_url(item.get("url"))
        external_id = _djinni_external_id(source_url, str(item.get("identifier") or ""))
        if not source_url or not external_id:
            continue
        description = _text_from_html(item.get("description"))
        salary = item.get("baseSalary") or {}
        currency = None
        salary_value = None
        if isinstance(salary, dict):
            salary_value = salary.get("value") or {}
            currency = salary.get("currency")
        compensation = None
        if isinstance(salary_value, dict):
            min_value = salary_value.get("minValue")
            max_value = salary_value.get("maxValue")
            if min_value and max_value:
                compensation = f"{currency or ''} {min_value}-{max_value}".strip()
            elif min_value:
                compensation = f"{currency or ''} {min_value}".strip()
        company = normalize_space(((item.get("hiringOrganization") or {}).get("name")))
        candidates.append(
            Candidate(
                external_id=external_id,
                title=title,
                source_url=source_url,
                apply_url=source_url,
                company=company or None,
                work_model=_infer_work_model(item.get("jobLocationType"), description),
                engagement_type=_infer_engagement_type(item.get("employmentType"), description),
                seniority=_infer_seniority(title),
                compensation_text=compensation,
                summary=_excerpt(description),
                description=description or None,
                first_seen_at=_optional_iso(item.get("datePosted")),
                last_seen_at=_optional_iso(item.get("validThrough")) or _optional_iso(item.get("datePosted")),
                metadata={"provider": "djinni", "json_ld": item},
            )
        )
    metrics.jobs_discovered = len(candidates)
    return candidates, None


def _enrich_djinni(candidate: Candidate, detail_html: str) -> Candidate:
    jobs = _parse_json_ld_jobs(detail_html)
    job = jobs[0] if jobs else {}
    soup = _soup(detail_html)
    description_node = soup.select_one("div.job-post__description")
    description = normalize_space(description_node.get_text(" ", strip=True) if description_node else "")
    title = normalize_space(job.get("title") or candidate.title)
    company = normalize_space(((job.get("hiringOrganization") or {}).get("name")) or candidate.company)
    return replace(
        candidate,
        title=title or candidate.title,
        company=company or candidate.company,
        work_model=_infer_work_model(job.get("jobLocationType"), description) or candidate.work_model,
        engagement_type=_infer_engagement_type(job.get("employmentType"), description)
        or candidate.engagement_type,
        seniority=_infer_seniority(title) or candidate.seniority,
        compensation_text=_find_money_text(description) or candidate.compensation_text,
        summary=_excerpt(description) or candidate.summary,
        description=description or candidate.description,
        metadata={**candidate.metadata, "provider": "djinni", "detail_json_ld": job},
    )


@register_source
class DjinniSource:
    slug = "djinni"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        provider_targets = ctx.provider_config
        metrics = ctx.metrics
        detail_limit = int(ctx.options.get("detail_limit") or 10)
        blockers: list[str] = []
        listed: list[Candidate] = []
        seen: set[str] = set()
        listing_urls = provider_targets.get("listing_urls") or [provider_targets.get("listing_url")]
        for listing_url in [url for url in listing_urls if url]:
            candidates, blocker = _parse_djinni_listing(
                ctx.fetcher.get_text(listing_url, "list"), ctx.role_lane, metrics
            )
            if blocker:
                blockers.append(f"{listing_url}: {blocker}")
            for candidate in candidates:
                if candidate.external_id in seen:
                    continue
                seen.add(candidate.external_id)
                listed.append(candidate)
        metrics.jobs_discovered = len(listed)
        if not listed:
            lane_name = normalize_space((ctx.targets.get("role_lane") or {}).get("name")) or "target"
            blockers.append(f"Djinni yielded zero {lane_name} candidates.")
            metrics.partial_blockers.extend(blockers)
            return [], "partial", blockers
        by_external_id, by_source_url = _load_existing_refs(ctx.conn, self.slug, listed)
        emitted: list[Candidate] = []
        detail_budget = detail_limit
        for candidate in listed:
            if _is_duplicate(candidate, by_external_id, by_source_url):
                metrics.jobs_skipped_as_duplicates += 1
                continue
            enriched = candidate
            if detail_budget > 0:
                try:
                    enriched = _enrich_djinni(candidate, ctx.fetcher.get_text(candidate.source_url, "detail"))
                    detail_budget -= 1
                except Exception as exc:
                    blockers.append(f"Djinni detail fetch failed for {candidate.source_url}: {exc}")
            else:
                metrics.detail_skipped_due_to_cap += 1
            emitted.append(enriched)
        status = "partial" if blockers else "completed"
        metrics.partial_blockers.extend(blockers)
        metrics.jobs_emitted = len(emitted)
        return emitted, status, blockers

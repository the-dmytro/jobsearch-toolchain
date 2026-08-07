from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from urllib.parse import urljoin, urlparse

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.registry import register_source
from jobtracker.sources.shared.infer import (
    _excerpt,
    _find_money_text,
    _infer_engagement_type,
    _infer_seniority,
    _infer_work_model,
    _matches_lane,
)
from jobtracker.sources.shared.parse import _soup
from jobtracker.sources.shared.payload import _is_duplicate, _load_existing_refs
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_name, normalize_space

_WORKUA_JOB_RE = re.compile(r"/jobs/(\d+)/")


def _workua_external_id(url: str | None) -> str | None:
    cleaned = clean_url(url)
    if not cleaned:
        return None
    match = _WORKUA_JOB_RE.search(urlparse(cleaned).path)
    return match.group(1) if match else None


def _workua_company_from_page_title(title_text: str | None) -> str | None:
    text = normalize_space(title_text)
    if not text:
        return None
    match = re.search(r"\bкомпанія\s+(.+?)(?:,\s*робота| — Work\.ua|$)", text, flags=re.IGNORECASE)
    return normalize_space(match.group(1)) if match else None


def _parse_workua_listing(listing_html: str, lane: dict[str, Any], metrics: Any) -> list[Candidate]:
    soup = _soup(listing_html)
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not href or not _WORKUA_JOB_RE.search(href):
            continue
        title = normalize_space(anchor.get_text(" ", strip=True))
        source_url = clean_url(urljoin("https://www.work.ua", href))
        external_id = _workua_external_id(source_url)
        if not title or not source_url or not external_id or external_id in seen:
            continue
        if not _matches_lane(title, lane):
            metrics.jobs_skipped_by_filter += 1
            continue
        seen.add(external_id)
        card = anchor.find_parent(["article", "div"])
        snippet = _excerpt(normalize_space(card.get_text(" ", strip=True) if card else title))
        candidates.append(
            Candidate(
                external_id=external_id,
                title=title,
                source_url=source_url,
                apply_url=source_url,
                seniority=_infer_seniority(title),
                summary=snippet,
                metadata={"provider": "workua"},
            )
        )
    metrics.jobs_discovered = len(candidates)
    return candidates


def _enrich_workua(candidate: Candidate, detail_html: str) -> Candidate:
    soup = _soup(detail_html)
    page_title = normalize_space(soup.title.get_text(" ", strip=True) if soup.title else "")
    title_node = soup.select_one("#h1-name") or soup.select_one("h1")
    title = normalize_space(title_node.get_text(" ", strip=True) if title_node else candidate.title)
    company_node = soup.select_one("a[href*='/jobs/by-company/']")
    company = (
        normalize_space(company_node.get_text(" ", strip=True) if company_node else "")
        or _workua_company_from_page_title(page_title)
        or normalize_space(candidate.company)
    )
    description_node = soup.select_one("#job-description")
    description = normalize_space(description_node.get_text(" ", strip=True) if description_node else "")
    detail_text = normalize_space(soup.get_text(" ", strip=True))
    location = None
    page_work_model = _infer_work_model(page_title)
    if page_work_model == "Remote" or "remote" in normalize_name(detail_text):
        location = "Remote"
    return replace(
        candidate,
        title=title or candidate.title,
        company=company or candidate.company,
        location=location or candidate.location,
        work_model=page_work_model or _infer_work_model(detail_text) or candidate.work_model,
        engagement_type=_infer_engagement_type(detail_text) or candidate.engagement_type,
        seniority=_infer_seniority(title) or candidate.seniority,
        compensation_text=_find_money_text(page_title) or candidate.compensation_text,
        summary=_excerpt(description) or candidate.summary,
        description=description or candidate.description,
        metadata={**candidate.metadata, "provider": "workua"},
    )


@register_source
class WorkuaSource:
    slug = "workua"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        lane = ctx.role_lane
        provider_targets = ctx.provider_config
        metrics = ctx.metrics
        max_pages = int(ctx.options.get("max_pages") or 1)
        detail_limit = int(ctx.options.get("detail_limit") or 10)
        blockers: list[str] = []
        listed: list[Candidate] = []
        seen: set[str] = set()
        for url in (provider_targets.get("listing_urls") or [])[: max_pages or 1]:
            for candidate in _parse_workua_listing(ctx.fetcher.get_text(url, "list"), lane, metrics):
                if candidate.external_id in seen:
                    continue
                seen.add(candidate.external_id)
                listed.append(candidate)
        metrics.jobs_discovered = len(listed)
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
                    enriched = _enrich_workua(candidate, ctx.fetcher.get_text(candidate.source_url, "detail"))
                    detail_budget -= 1
                except Exception as exc:
                    blockers.append(f"Work.ua detail fetch failed for {candidate.source_url}: {exc}")
            else:
                metrics.detail_skipped_due_to_cap += 1
            emitted.append(enriched)
        status = "partial" if blockers else "completed"
        metrics.partial_blockers.extend(blockers)
        metrics.jobs_emitted = len(emitted)
        return emitted, status, blockers

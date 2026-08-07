from __future__ import annotations

import xml.etree.ElementTree as ET
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
    _optional_iso,
)
from jobtracker.sources.shared.parse import _first_link_text_from_html, _soup, _text_from_html
from jobtracker.sources.shared.payload import _is_duplicate, _load_existing_refs, _needs_detail
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_name, normalize_space


def _dou_external_id(url: str | None) -> str | None:
    cleaned = clean_url(url)
    if not cleaned:
        return None
    path = urlparse(cleaned).path.strip("/")
    return path or None


def _parse_dou_rss(feed_text: str, lane: dict[str, Any], metrics: Any) -> list[Candidate]:
    root = ET.fromstring(feed_text)
    items = root.findall(".//item")
    candidates: list[Candidate] = []
    for item in items:
        title = normalize_space(item.findtext("title"))
        if not _matches_lane(title, lane):
            metrics.jobs_skipped_by_filter += 1
            continue
        source_url = clean_url(item.findtext("link"))
        external_id = _dou_external_id(source_url)
        if not source_url or not external_id:
            continue
        description_html = item.findtext("description")
        summary = _excerpt(_text_from_html(description_html))
        published_at = _optional_iso(item.findtext("pubDate"))
        candidates.append(
            Candidate(
                external_id=external_id,
                title=title,
                source_url=source_url,
                apply_url=source_url,
                company=_first_link_text_from_html(description_html),
                seniority=_infer_seniority(title),
                summary=summary,
                first_seen_at=published_at,
                last_seen_at=published_at,
                metadata={
                    "provider": "dou",
                    "guid": normalize_space(item.findtext("guid")),
                    "rss_description_html": description_html,
                },
            )
        )
    metrics.jobs_discovered = len(candidates)
    return candidates


def _parse_dou_listing(listing_html: str, lane: dict[str, Any], metrics: Any) -> list[Candidate]:
    soup = _soup(listing_html)
    seen: set[str] = set()
    candidates: list[Candidate] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not href or "/companies/" not in href or "/vacancies/" not in href:
            continue
        source_url = clean_url(urljoin("https://jobs.dou.ua", href))
        external_id = _dou_external_id(source_url)
        title = normalize_space(anchor.get_text(" ", strip=True))
        if not source_url or not external_id or external_id in seen or not _matches_lane(title, lane):
            if title and not _matches_lane(title, lane):
                metrics.jobs_skipped_by_filter += 1
            continue
        seen.add(external_id)
        candidates.append(
            Candidate(
                external_id=external_id,
                title=title,
                source_url=source_url,
                apply_url=source_url,
                seniority=_infer_seniority(title),
                metadata={"provider": "dou", "listing_fallback": True},
            )
        )
    metrics.jobs_discovered = len(candidates)
    return candidates


def _enrich_dou(candidate: Candidate, detail_html: str) -> Candidate:
    soup = _soup(detail_html)
    title = normalize_space(
        (soup.select_one("h1.g-h2") or soup.select_one("h1")).get_text(" ", strip=True)
        if soup.select_one("h1.g-h2") or soup.select_one("h1")
        else candidate.title
    )
    company = ""
    for company_node in soup.select("div.b-compinfo a.company, div.b-compinfo a[href*='/companies/']"):
        company_text = normalize_space(company_node.get_text(" ", strip=True))
        if company_text and normalize_name(company_text) != "всі вакансії компанії":
            company = company_text
            break
    company = company or normalize_space(candidate.company)
    description_node = soup.select_one("div.l-vacancy")
    description = normalize_space(description_node.get_text(" ", strip=True) if description_node else "")
    header_node = soup.select_one("div.sh-info")
    header_text = normalize_space(header_node.get_text(" ", strip=True) if header_node else "")
    return replace(
        candidate,
        title=title or candidate.title,
        company=company or candidate.company,
        work_model=_infer_work_model(header_text, description) or candidate.work_model,
        engagement_type=_infer_engagement_type(header_text, description) or candidate.engagement_type,
        seniority=_infer_seniority(title) or candidate.seniority,
        compensation_text=_find_money_text(header_text) or _find_money_text(description) or candidate.compensation_text,
        summary=_excerpt(description) or candidate.summary,
        description=description or candidate.description,
        metadata={**candidate.metadata, "provider": "dou", "header_text": header_text},
    )


@register_source
class DouSource:
    slug = "dou"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        provider_targets = ctx.provider_config
        blockers: list[str] = []
        lane = ctx.role_lane
        metrics = ctx.metrics
        detail_limit = int(ctx.options.get("detail_limit") or 10)
        candidates: list[Candidate] = []
        seen: set[str] = set()
        feed_urls = provider_targets.get("feed_urls") or [provider_targets.get("feed_url")]
        for feed_url in [url for url in feed_urls if url]:
            try:
                for candidate in _parse_dou_rss(ctx.fetcher.get_text(feed_url, "list"), lane, metrics):
                    if candidate.external_id in seen:
                        continue
                    seen.add(candidate.external_id)
                    candidates.append(candidate)
            except Exception as exc:
                blockers.append(f"DOU RSS fetch failed for {feed_url}: {exc}")
        if not candidates:
            listing_urls = provider_targets.get("listing_urls") or [provider_targets.get("listing_url")]
            for listing_url in [url for url in listing_urls if url]:
                try:
                    for candidate in _parse_dou_listing(ctx.fetcher.get_text(listing_url, "list"), lane, metrics):
                        if candidate.external_id in seen:
                            continue
                        seen.add(candidate.external_id)
                        candidates.append(candidate)
                except Exception as exc:
                    blockers.append(f"DOU HTML fallback failed for {listing_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        if not candidates and blockers:
            metrics.partial_blockers.extend(blockers)
            return [], "partial", blockers
        by_external_id, by_source_url = _load_existing_refs(ctx.conn, self.slug, candidates)
        emitted: list[Candidate] = []
        detail_budget = detail_limit
        for candidate in candidates:
            duplicate = _is_duplicate(candidate, by_external_id, by_source_url)
            needs_detail = _needs_detail(candidate, self.slug, by_external_id, by_source_url)
            if duplicate and not needs_detail:
                metrics.jobs_skipped_as_duplicates += 1
                continue
            enriched = candidate
            if needs_detail and detail_budget > 0:
                try:
                    enriched = _enrich_dou(candidate, ctx.fetcher.get_text(candidate.source_url, "detail"))
                    detail_budget -= 1
                except Exception as exc:
                    blockers.append(f"DOU detail fetch failed for {candidate.source_url}: {exc}")
            elif needs_detail:
                metrics.detail_skipped_due_to_cap += 1
            emitted.append(enriched)
        status = "partial" if blockers else "completed"
        metrics.partial_blockers.extend(blockers)
        metrics.jobs_emitted = len(emitted)
        return emitted, status, blockers

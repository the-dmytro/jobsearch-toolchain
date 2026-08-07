from __future__ import annotations

import re
from typing import Any

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.db import fetch_all
from jobtracker.sources.registry import register_source
from jobtracker.sources.shared.infer import (
    _excerpt,
    _infer_seniority,
    _infer_work_model,
    _matches_lane,
    _optional_iso,
)
from jobtracker.sources.shared.parse import _text_from_html
from jobtracker.sources.shared.payload import _is_duplicate, _load_existing_refs
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space

_GREENHOUSE_BOARD_RE = re.compile(r"https?://(?:job-boards|boards)\.greenhouse\.io/([^/?#]+)/jobs", re.IGNORECASE)


def _greenhouse_external_id(board_token: str, job_id: Any) -> str:
    return f"gh:{board_token}:{job_id}"


def _greenhouse_board_from_url(url: str | None) -> str | None:
    text = normalize_space(url)
    if not text:
        return None
    match = _GREENHOUSE_BOARD_RE.search(text)
    if match:
        return normalize_space(match.group(1)).lower()
    return None


def _load_greenhouse_board_tokens_from_db(conn: Any | None) -> list[str]:
    if not conn:
        return []
    rows = fetch_all(
        conn,
        """
        select url
        from (
          select source_url as url from opportunities where source_url ilike %s
          union
          select apply_url as url from opportunities where apply_url ilike %s
          union
          select source_url as url from source_items where source_url ilike %s
        ) greenhouse_urls
        where url is not null
        order by url
        """,
        ("%greenhouse%", "%greenhouse%", "%greenhouse%"),
    )
    tokens: list[str] = []
    seen: set[str] = set()
    for row in rows:
        token = _greenhouse_board_from_url(row.get("url"))
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _parse_greenhouse_jobs(payload: dict[str, Any], board_token: str, lane: dict[str, Any], metrics: Any) -> list[Candidate]:
    candidates: list[Candidate] = []
    for item in payload.get("jobs") or []:
        title = normalize_space(item.get("title"))
        if not _matches_lane(title, lane):
            metrics.jobs_skipped_by_filter += 1
            continue
        source_url = clean_url(item.get("absolute_url"))
        if not source_url:
            continue
        content = _text_from_html(item.get("content"))
        location = normalize_space(((item.get("location") or {}).get("name")))
        company = normalize_space(item.get("company_name"))
        candidates.append(
            Candidate(
                external_id=_greenhouse_external_id(board_token, item.get("id")),
                title=title,
                source_url=source_url,
                apply_url=source_url,
                company=company or None,
                location=location or None,
                work_model=_infer_work_model(location, content),
                seniority=_infer_seniority(title),
                summary=_excerpt(content),
                description=content or None,
                first_seen_at=_optional_iso(item.get("first_published")),
                last_seen_at=_optional_iso(item.get("updated_at")) or _optional_iso(item.get("first_published")),
                metadata={
                    "provider": "greenhouse",
                    "board_token": board_token,
                    "company_name": item.get("company_name"),
                    "internal_job_id": item.get("internal_job_id"),
                    "requisition_id": item.get("requisition_id"),
                    "departments": item.get("departments"),
                    "offices": item.get("offices"),
                },
            )
        )
    metrics.jobs_discovered += len(candidates)
    return candidates


@register_source
class GreenhouseSource:
    slug = "greenhouse"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        provider_targets = ctx.provider_config
        metrics = ctx.metrics
        explicit_tokens = ctx.options.get("board_tokens")
        max_boards = ctx.options.get("max_boards")
        denylist = {normalize_space(token).lower() for token in provider_targets.get("denylist") or [] if normalize_space(token)}
        auto_tokens = _load_greenhouse_board_tokens_from_db(ctx.conn)
        manual_tokens = [
            normalize_space(token).lower()
            for token in provider_targets.get("manual_board_tokens") or []
            if normalize_space(token)
        ]
        chosen_tokens: list[str] = []
        for token in (explicit_tokens or []) + auto_tokens + manual_tokens:
            normalized = normalize_space(token).lower()
            if not normalized or normalized in denylist or normalized in chosen_tokens:
                continue
            chosen_tokens.append(normalized)
        if max_boards:
            chosen_tokens = chosen_tokens[:max_boards]
        metrics.board_tokens = chosen_tokens
        if not chosen_tokens:
            blocker = "No Greenhouse board tokens were available from DB history or manual overrides."
            metrics.partial_blockers.append(blocker)
            return [], "partial", [blocker]
        candidates: list[Candidate] = []
        blockers: list[str] = []
        for token in chosen_tokens:
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
            try:
                payload = ctx.fetcher.get_json(url, "api")
                candidates.extend(_parse_greenhouse_jobs(payload, token, ctx.role_lane, metrics))
            except Exception as exc:
                blockers.append(f"Greenhouse board {token} failed: {exc}")
        by_external_id, by_source_url = _load_existing_refs(ctx.conn, self.slug, candidates)
        emitted: list[Candidate] = []
        for candidate in candidates:
            if _is_duplicate(candidate, by_external_id, by_source_url):
                metrics.jobs_skipped_as_duplicates += 1
                continue
            emitted.append(candidate)
        status = "partial" if blockers else "completed"
        metrics.partial_blockers.extend(blockers)
        metrics.jobs_emitted = len(emitted)
        return emitted, status, blockers

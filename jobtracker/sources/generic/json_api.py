from __future__ import annotations

from typing import Any

from jobtracker.core.models import Candidate, CollectionContext
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


class JsonApiSource:
    slug: str = "json_api"
    api_url_template: str = ""
    jobs_key: str | None = "jobs"
    external_id_prefix: str = ""

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def _extract_jobs(self, payload: Any) -> list[dict[str, Any]]:
        if self.jobs_key is None:
            return payload if isinstance(payload, list) else []
        if isinstance(payload, dict):
            jobs = payload.get(self.jobs_key) or []
            return jobs if isinstance(jobs, list) else []
        return []

    def _parse_job(
        self, item: dict[str, Any], token: str, lane: dict[str, Any], metrics: Any
    ) -> Candidate | None:
        title = normalize_space(item.get("title") or item.get("text"))
        if not _matches_lane(title, lane):
            metrics.jobs_skipped_by_filter += 1
            return None
        source_url = clean_url(
            item.get("absolute_url") or item.get("hostedUrl") or item.get("jobUrl") or item.get("applyUrl")
        )
        if not source_url:
            return None
        job_id = item.get("id")
        external_id = (
            f"{self.external_id_prefix}{token}:{job_id}"
            if self.external_id_prefix
            else str(job_id or source_url)
        )
        content = _text_from_html(
            item.get("content") or item.get("descriptionPlain") or item.get("description")
        )
        location = normalize_space(
            (
                (item.get("location") or {}).get("name")
                if isinstance(item.get("location"), dict)
                else item.get("location")
            )
            or ((item.get("categories") or {}).get("location"))
        )
        company = normalize_space(item.get("company_name") or item.get("company"))
        return Candidate(
            external_id=external_id,
            title=title,
            source_url=source_url,
            apply_url=source_url,
            company=company or None,
            location=location or None,
            work_model=_infer_work_model(location, content),
            seniority=_infer_seniority(title),
            summary=_excerpt(content),
            description=content or None,
            first_seen_at=_optional_iso(item.get("first_published") or item.get("createdAt")),
            last_seen_at=_optional_iso(
                item.get("updated_at") or item.get("updatedAt") or item.get("first_published")
            ),
            metadata={"provider": self.slug, "board_token": token},
        )

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        provider_config = ctx.provider_config
        tokens = (
            opts.get("board_tokens") or opts.get("tokens") or provider_config.get("manual_board_tokens") or []
        )
        max_boards = opts.get("max_boards")
        lane = ctx.role_lane
        metrics = ctx.metrics
        if max_boards:
            tokens = tokens[:max_boards]
        metrics.board_tokens = list(tokens)
        candidates: list[Candidate] = []
        blockers: list[str] = []
        for token in tokens:
            url = self.api_url_template.format(token=token, board=token)
            try:
                payload = ctx.fetcher.get_json(url, "api")
                for item in self._extract_jobs(payload):
                    if not isinstance(item, dict):
                        continue
                    candidate = self._parse_job(item, token, lane, metrics)
                    if candidate:
                        candidates.append(candidate)
            except Exception as exc:
                blockers.append(f"{self.slug} board {token} failed: {exc}")
        metrics.jobs_discovered = len(candidates)
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

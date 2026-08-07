from __future__ import annotations

import csv
import io

from jobtracker.core.models import Candidate, CollectionContext
from jobtracker.sources.shared.infer import _infer_seniority, _matches_lane
from jobtracker.url_tools import clean_url
from jobtracker.utils import normalize_space


class CsvSource:
    slug: str = "csv"

    def health(self, ctx: CollectionContext) -> list[str]:
        return []

    def discover(self, ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]:
        opts = ctx.options
        csv_urls = opts.get("csv_urls") or [opts.get("csv_url")]
        title_col = opts.get("title_column", "title")
        url_col = opts.get("url_column", "url")
        company_col = opts.get("company_column", "company")
        lane = ctx.role_lane
        metrics = ctx.metrics
        candidates: list[Candidate] = []
        blockers: list[str] = []
        for csv_url in [url for url in csv_urls if url]:
            try:
                text = ctx.fetcher.get_text(csv_url, "list")
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    title = normalize_space(row.get(title_col))
                    if not _matches_lane(title, lane):
                        metrics.jobs_skipped_by_filter += 1
                        continue
                    source_url = clean_url(row.get(url_col))
                    if not source_url:
                        continue
                    candidates.append(
                        Candidate(
                            external_id=source_url,
                            title=title,
                            source_url=source_url,
                            apply_url=source_url,
                            company=normalize_space(row.get(company_col)) or None,
                            seniority=_infer_seniority(title),
                            metadata={"provider": self.slug},
                        )
                    )
            except Exception as exc:
                blockers.append(f"CSV fetch failed for {csv_url}: {exc}")
        metrics.jobs_discovered = len(candidates)
        metrics.jobs_emitted = len(candidates)
        status = "partial" if blockers else "completed"
        return candidates, status, blockers

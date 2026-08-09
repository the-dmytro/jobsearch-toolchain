from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..base import DuplicateMatch, UpsertResult


class MemoryJobStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self._opportunities_by_run: dict[str, list[dict[str, Any]]] = {}
        self.duplicates: dict[tuple[str, str], list[DuplicateMatch]] = {}

    @property
    def opportunities(self) -> list[dict[str, Any]]:
        return [item for items in self._opportunities_by_run.values() for item in items]

    def _rebuild_duplicates(self) -> None:
        self.duplicates = {}
        for run_key, run in self.runs.items():
            provider_slug = str(run["provider"])
            for opportunity in self._opportunities_by_run.get(run_key, []):
                external_id = str(opportunity.get("external_id") or "").strip()
                if not external_id:
                    continue
                match = DuplicateMatch(
                    match_type="external_id",
                    opportunity_id=str(opportunity.get("id") or external_id),
                    company=opportunity.get("company"),
                    title=opportunity.get("title"),
                    source_url=opportunity.get("source_url"),
                    apply_url=opportunity.get("apply_url"),
                )
                self.duplicates.setdefault((provider_slug, external_id), []).append(match)
                company = str(opportunity.get("company") or "").strip().lower()
                title = str(opportunity.get("title") or "").strip().lower()
                if company and title:
                    self.duplicates.setdefault((provider_slug, f"title:{company}:{title}"), []).append(match)

    def upsert_run_payload(
        self,
        provider_slug: str,
        payload_path: str,
        report_path: str | None = None,
    ) -> UpsertResult:
        payload = json.loads(Path(payload_path).read_text(encoding="utf-8"))
        run = payload.get("run") or {}
        run_key = str(run.get("run_key") or payload.get("run_key") or f"{provider_slug}-memory")
        opportunities = payload.get("opportunities") or payload.get("jobs") or []
        evaluations = sum(1 for item in opportunities if item.get("evaluation"))
        self.runs[run_key] = {
            "provider": provider_slug,
            "payload": payload,
            "report_path": report_path,
        }
        self._opportunities_by_run[run_key] = list(opportunities)
        self._rebuild_duplicates()
        return UpsertResult(run_key=run_key, opportunities=len(opportunities), evaluations=evaluations)

    def check_duplicates(
        self,
        provider_slug: str,
        company: str | None,
        title: str | None,
        external_id: str | None = None,
    ) -> list[DuplicateMatch]:
        matches: list[DuplicateMatch] = []
        seen: set[str] = set()
        keys: list[tuple[str, str]] = []
        if external_id:
            keys.append((provider_slug, external_id))
        company_key = str(company or "").strip().lower()
        title_key = str(title or "").strip().lower()
        if company_key and title_key:
            keys.append((provider_slug, f"title:{company_key}:{title_key}"))
        for key in keys:
            for match in self.duplicates.get(key, []):
                marker = f"{match.match_type}:{match.opportunity_id}:{match.title}:{match.source_url}"
                if marker in seen:
                    continue
                seen.add(marker)
                matches.append(match)
        return matches

    def export_application_summary(self, application_id: str) -> str:
        return f"# Application summary\n\n- Application ID: {application_id}\n"

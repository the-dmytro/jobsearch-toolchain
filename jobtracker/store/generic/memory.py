from __future__ import annotations

from typing import Any

from ..base import DuplicateMatch, JobStore, UpsertResult


class MemoryJobStore:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.opportunities: list[dict[str, Any]] = []
        self.duplicates: dict[tuple[str, str], list[DuplicateMatch]] = {}

    def upsert_run_payload(
        self,
        provider_slug: str,
        payload_path: str,
        report_path: str | None = None,
    ) -> UpsertResult:
        import json
        from pathlib import Path

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
        self.opportunities.extend(opportunities)
        return UpsertResult(run_key=run_key, opportunities=len(opportunities), evaluations=evaluations)

    def check_duplicates(
        self,
        provider_slug: str,
        company: str | None,
        title: str | None,
        external_id: str | None = None,
    ) -> list[DuplicateMatch]:
        key = (provider_slug, external_id or "")
        return list(self.duplicates.get(key, []))

    def export_application_summary(self, application_id: str) -> str:
        return f"# Application summary\n\n- Application ID: {application_id}\n"

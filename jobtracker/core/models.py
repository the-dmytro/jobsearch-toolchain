from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ConnectorBuildContext:
    root: Path
    slug: str
    options: Mapping[str, Any]


@dataclass
class FetchMetrics:
    request_count: int = 0
    retry_count: int = 0
    list_request_count: int = 0
    detail_request_count: int = 0
    api_request_count: int = 0
    list_latency_ms: int = 0
    detail_latency_ms: int = 0
    api_latency_ms: int = 0
    jobs_discovered: int = 0
    jobs_emitted: int = 0
    jobs_skipped_as_duplicates: int = 0
    jobs_skipped_by_filter: int = 0
    detail_skipped_due_to_cap: int = 0
    payload_size_bytes: int = 0
    board_tokens: list[str] = field(default_factory=list)
    partial_blockers: list[str] = field(default_factory=list)

    def record_request(self, kind: str, latency_ms: int, retried: bool = False) -> None:
        self.request_count += 1
        if retried:
            self.retry_count += 1
        if kind == "detail":
            self.detail_request_count += 1
            self.detail_latency_ms += latency_ms
        elif kind == "api":
            self.api_request_count += 1
            self.api_latency_ms += latency_ms
        else:
            self.list_request_count += 1
            self.list_latency_ms += latency_ms

    def to_dict(self, status: str) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "list_request_count": self.list_request_count,
            "detail_request_count": self.detail_request_count,
            "api_request_count": self.api_request_count,
            "list_latency_ms": self.list_latency_ms,
            "detail_latency_ms": self.detail_latency_ms,
            "api_latency_ms": self.api_latency_ms,
            "jobs_discovered": self.jobs_discovered,
            "jobs_emitted": self.jobs_emitted,
            "jobs_skipped_as_duplicates": self.jobs_skipped_as_duplicates,
            "jobs_skipped_by_filter": self.jobs_skipped_by_filter,
            "detail_skipped_due_to_cap": self.detail_skipped_due_to_cap,
            "payload_size_bytes": self.payload_size_bytes,
            "board_tokens": self.board_tokens,
            "run_status": status,
            "partial_blockers": self.partial_blockers,
        }


@dataclass(frozen=True)
class ExistingRef:
    external_id: str | None
    source_url: str | None
    last_seen_at: datetime | None


@dataclass(frozen=True)
class Candidate:
    external_id: str
    title: str
    source_url: str
    apply_url: str
    company: str | None = None
    location: str | None = None
    work_model: str | None = None
    engagement_type: str | None = None
    seniority: str | None = None
    compensation_text: str | None = None
    summary: str | None = None
    description: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def source_item_id(self, provider_slug: str) -> str:
        return f"{provider_slug}:{self.external_id}"

    def as_source_item(self, provider_slug: str) -> dict[str, Any]:
        return {
            "source_type": "job_posting",
            "external_id": self.source_item_id(provider_slug),
            "source_url": self.source_url,
            "timestamp": self.last_seen_at or self.first_seen_at,
            "title": self.title,
            "summary": self.summary,
            "raw_text": self.description,
            "provider_metadata": self.metadata,
        }

    def as_opportunity(self, provider_slug: str) -> dict[str, Any]:
        return {
            "opportunity_type": "employment",
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "source_url": self.source_url,
            "apply_url": self.apply_url,
            "location": self.location,
            "work_model": self.work_model,
            "engagement_type": self.engagement_type,
            "seniority": self.seniority,
            "compensation_text": self.compensation_text,
            "source_status": "discovered",
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "source_items": [self.source_item_id(provider_slug)],
            "provider_metadata": self.metadata,
        }


@dataclass
class CollectionContext:
    conn: Any | None = None
    fetcher: Any = None
    targets: dict[str, Any] = field(default_factory=dict)
    metrics: FetchMetrics = field(default_factory=FetchMetrics)
    provider_slug: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def role_lane(self) -> dict[str, Any]:
        return self.targets.get("role_lane") or {}

    @property
    def provider_config(self) -> dict[str, Any]:
        providers = self.targets.get("providers") or {}
        return providers.get(self.provider_slug) or {}


@dataclass
class CollectionResult:
    provider_slug: str
    candidates: list[Candidate]
    status: str
    summary: str
    blockers: list[str]
    metrics: FetchMetrics
    run_key: str
    payload: dict[str, Any]
    payload_path: Path | None
    persisted: bool = False
    persisted_result: dict[str, Any] | None = None

    def to_dict(self, dry_run: bool) -> dict[str, Any]:
        return {
            "provider": self.provider_slug,
            "dry_run": dry_run,
            "status": self.status,
            "summary": self.summary,
            "run_key": self.run_key,
            "payload_path": str(self.payload_path) if self.payload_path else None,
            "opportunities": len(self.candidates),
            "source_items": len(self.payload.get("source_items") or []),
            "blockers": self.blockers,
            "metrics": self.metrics.to_dict(self.status),
            "persisted": self.persisted,
            "persisted_result": self.persisted_result,
        }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class UpsertResult:
    run_key: str
    opportunities: int
    evaluations: int
    stored_texts: int = 0
    report_document_id: str | None = None


@dataclass(frozen=True)
class DuplicateMatch:
    match_type: str
    opportunity_id: str | None = None
    title: str | None = None
    source_url: str | None = None
    apply_url: str | None = None
    location_text: str | None = None
    work_model: str | None = None
    company: str | None = None
    application_id: str | None = None
    application_status: str | None = None
    applied_at: str | None = None
    automation_run_keys: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_type": self.match_type,
            "opportunity_id": self.opportunity_id,
            "title": self.title,
            "source_url": self.source_url,
            "apply_url": self.apply_url,
            "location_text": self.location_text,
            "work_model": self.work_model,
            "company": self.company,
            "application_id": self.application_id,
            "application_status": self.application_status,
            "applied_at": self.applied_at,
            "automation_run_keys": self.automation_run_keys,
        }


@dataclass(frozen=True)
class ArtifactRef:
    local_path: str | None = None
    storage_bucket: str | None = None
    storage_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    uploaded: bool = False
    upload_warning: str | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "local_path": self.local_path,
            "storage_bucket": self.storage_bucket,
            "storage_path": self.storage_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "uploaded": self.uploaded,
        }
        if self.upload_warning:
            payload["upload_warning"] = self.upload_warning
        if self.metadata:
            payload.update(self.metadata)
        return payload


class JobStore(Protocol):
    def upsert_run_payload(
        self,
        provider_slug: str,
        payload_path: str,
        report_path: str | None = None,
    ) -> UpsertResult: ...

    def check_duplicates(
        self,
        provider_slug: str,
        company: str | None,
        title: str | None,
        external_id: str | None = None,
    ) -> list[DuplicateMatch]: ...

    def export_application_summary(self, application_id: str) -> str: ...


class ArtifactStore(Protocol):
    def upload(self, path: str, storage_path: str | None = None) -> ArtifactRef: ...

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

from .utils import normalize_space, slugify

_UPWORK_URL_RE = re.compile(r"/jobs/\~?([A-Za-z0-9]+)")
_LINKEDIN_URL_RE = re.compile(r"/jobs/view/(\d+)")


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str]
    warnings: list[str]
    normalized: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "normalized": self.normalized,
            "summary": {
                "source_items": len(
                    self.normalized.get("source_items") or self.normalized.get("emails") or []
                ),
                "opportunities": len(
                    self.normalized.get("opportunities") or self.normalized.get("jobs") or []
                ),
            },
        }


def normalize_provider_external_id(provider: str, value: Any) -> str | None:
    text = normalize_space(str(value) if value is not None else "")
    if not text:
        return None
    provider_slug = slugify(provider)
    if provider_slug == "upwork":
        match = _UPWORK_URL_RE.search(text)
        if match:
            return match.group(1)
        leaf = text.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        return leaf.lstrip("~") or None
    if provider_slug == "linkedin":
        match = _LINKEDIN_URL_RE.search(text)
        if match:
            return match.group(1)
        if text.isdigit():
            return text
    return text


def validate_payload(payload: dict[str, Any], provider: str) -> ValidationResult:
    normalized = copy.deepcopy(payload)
    errors: list[str] = []
    warnings: list[str] = []

    run = normalized.get("run")
    if not isinstance(run, dict):
        errors.append("run must be an object")
        run = {}
        normalized["run"] = run
    if not normalize_space(run.get("run_key")):
        warnings.append("run.run_key is missing; upsert-run will derive one from timestamps")
    status = normalize_space(run.get("status"))
    if status and status not in {"completed", "partial", "failed"}:
        warnings.append(f"run.status has non-standard value: {status}")

    source_items = normalized.get("source_items")
    if source_items is None and isinstance(normalized.get("emails"), list):
        source_items = normalized.get("emails")
        normalized["source_items"] = source_items
        warnings.append("legacy top-level 'emails' was read as canonical 'source_items'")
    if source_items is None:
        source_items = []
        normalized["source_items"] = source_items
    if source_items is not None and not isinstance(source_items, list):
        errors.append("source_items must be a list when present")
        source_items = []
    source_refs: set[str] = set()
    for index, source in enumerate(source_items or []):
        if not isinstance(source, dict):
            errors.append(f"source_items[{index}] must be an object")
            continue
        external_id = normalize_space(
            source.get("external_id") or source.get("message_id") or source.get("id")
        )
        if external_id:
            source_refs.add(external_id)
        else:
            warnings.append(f"source_items[{index}].external_id is missing")
        if not normalize_space(source.get("source_type")):
            source["source_type"] = "email"

    opportunities = normalized.get("opportunities")
    if opportunities is None and isinstance(normalized.get("jobs"), list):
        opportunities = normalized.get("jobs")
        normalized["opportunities"] = opportunities
        warnings.append("legacy top-level 'jobs' was read as canonical 'opportunities'")
    if opportunities is None:
        opportunities = []
        normalized["opportunities"] = opportunities
    if not isinstance(opportunities, list):
        errors.append("opportunities must be a list")
        opportunities = []

    for index, opportunity in enumerate(opportunities):
        if not isinstance(opportunity, dict):
            errors.append(f"opportunities[{index}] must be an object")
            continue
        title = normalize_space(
            opportunity.get("title") or opportunity.get("role_title") or opportunity.get("job_title")
        )
        if not title:
            errors.append(f"opportunities[{index}].title is required")
        external_id = normalize_provider_external_id(
            provider, opportunity.get("external_id") or opportunity.get("provider_external_id")
        )
        if not external_id:
            external_id = normalize_provider_external_id(
                provider,
                opportunity.get("source_url") or opportunity.get("job_url") or opportunity.get("url"),
            )
        if external_id:
            opportunity["external_id"] = external_id
        else:
            errors.append(f"opportunities[{index}] needs external_id or source_url")
        source_url = normalize_space(
            opportunity.get("source_url") or opportunity.get("job_url") or opportunity.get("url")
        )
        if source_url and not opportunity.get("source_url"):
            opportunity["source_url"] = source_url
        for source_ref in opportunity.get("source_items") or []:
            if isinstance(source_ref, str) and source_refs and source_ref not in source_refs:
                warnings.append(
                    f"opportunities[{index}].source_items references unknown source item: {source_ref}"
                )
        evaluation = opportunity.get("evaluation")
        if evaluation is not None and not isinstance(evaluation, dict):
            warnings.append(f"opportunities[{index}].evaluation should be an object")

    return ValidationResult(errors=errors, warnings=warnings, normalized=normalized)

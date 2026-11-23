from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from jobtracker.core.connectors import ConnectorSpec
from jobtracker.core.errors import UnknownConnectorError
from jobtracker.core.models import CollectionContext, CollectionResult, ConnectorBuildContext, FetchMetrics
from jobtracker.core.registry import Registry
from jobtracker.payloads import upsert_run_payload
from jobtracker.sources.base import JobSource
from jobtracker.sources.generic.csv import CsvSource
from jobtracker.sources.generic.html import HtmlSource
from jobtracker.sources.generic.json_api import JsonApiSource
from jobtracker.sources.generic.jsonld import JsonLdSource
from jobtracker.sources.generic.rss import RssSource
from jobtracker.sources.generic.sitemap import SitemapSource
from jobtracker.sources.shared.fetch import FIXTURE_ROOT, FixtureFetcher, LiveFetcher
from jobtracker.sources.shared.payload import _build_payload, _json, _payload_path, _write_payload
from jobtracker.store.base import JobStore
from jobtracker.utils import normalize_space, slugify, utc_now

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_TARGETS = _REPO_ROOT / "profile" / "provider_targets.toml"
_FIXTURE_TARGETS = Path(__file__).resolve().parents[1] / "fixtures" / "provider_targets.toml"
TARGETS_PATH = _PROFILE_TARGETS if _PROFILE_TARGETS.exists() else _FIXTURE_TARGETS
DEFAULT_JOBSEARCH_CONFIG = _REPO_ROOT / "config" / "jobsearch.toml"

source_registry: Registry[Any] = Registry("source")

GENERIC_SOURCE_KINDS: dict[str, type] = {
    "rss": RssSource,
    "jsonld": JsonLdSource,
    "html": HtmlSource,
    "json_api": JsonApiSource,
    "json-api": JsonApiSource,
    "sitemap": SitemapSource,
    "csv": CsvSource,
}

T = TypeVar("T", bound=type)


def register_source(cls: T) -> T:
    instance = cls()
    source_registry.register(instance)
    return cls


def _load_targets(
    path: str | Path | None = None, *, root: Path | None = None, fixture_mode: bool = False
) -> dict[str, Any]:
    """Load provider targets from an explicit path or the selected root's profile.

    Bundled fixture targets are used only in fixture mode; a missing private targets
    file is an error, never silently replaced by example companies.
    """
    selected = path or os.getenv("JOBTRACKER_PROVIDER_TARGETS")
    if selected:
        target_path = Path(selected)
        if root and not target_path.is_absolute():
            target_path = root / target_path
    else:
        target_path = (root or _REPO_ROOT) / "profile/provider_targets.toml"
        if not target_path.exists():
            if not fixture_mode:
                raise ValueError(
                    f"Provider targets not found at {target_path}. Create it from "
                    "profile/templates/generic/provider_targets.toml or pass --targets."
                )
            target_path = _FIXTURE_TARGETS
    return tomllib.loads(target_path.read_text(encoding="utf-8"))


def _load_jobsearch_sources(
    *,
    config_path: str | Path | None = None,
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    project_root = root or _REPO_ROOT
    path = Path(config_path) if config_path else project_root / "config" / "jobsearch.toml"
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        example = project_root / "config" / "jobsearch.example.toml"
        path = example if example.exists() else path
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sources_raw = data.get("sources") or {}
    if not isinstance(sources_raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for slug, config in sources_raw.items():
        if isinstance(config, dict):
            result[slugify(str(slug))] = dict(config)
    local_path = path.with_name(path.stem + ".local.toml")
    if local_path.exists():
        local_data = tomllib.loads(local_path.read_text(encoding="utf-8"))
        local_sources = local_data.get("sources") or {}
        if isinstance(local_sources, dict):
            for slug, config in local_sources.items():
                if isinstance(config, dict):
                    key = slugify(str(slug))
                    result[key] = {**result.get(key, {}), **config}
    return result


def _normalize_kind(kind: str | None) -> str | None:
    if not kind:
        return None
    return str(kind).strip().lower()


def build_generic_source(kind: str, slug: str) -> JobSource:
    normalized = _normalize_kind(kind) or ""
    # Accept both json_api and json-api
    cls = GENERIC_SOURCE_KINDS.get(normalized) or GENERIC_SOURCE_KINDS.get(normalized.replace("-", "_"))
    if cls is None:
        available = ", ".join(sorted({k for k in GENERIC_SOURCE_KINDS})) or "(none)"
        raise UnknownConnectorError(f"Unknown source kind {kind!r}. Available: {available}")
    instance = cls()
    instance.slug = slugify(slug)
    return instance


def resolve_source(
    provider_slug: str,
    *,
    source_config: dict[str, Any] | None = None,
    provider_targets: dict[str, Any] | None = None,
    root: Path | None = None,
) -> JobSource:
    slug = slugify(provider_slug)
    config = dict(source_config or {})
    targets = dict(provider_targets or {})
    kind = config.get("kind") or targets.get("kind")
    if kind:
        return build_generic_source(str(kind), slug)
    try:
        item = source_registry.get(slug)
        if isinstance(item, ConnectorSpec):
            context = ConnectorBuildContext(
                root=root or _REPO_ROOT,
                slug=slug,
                options={**targets, **config},
            )
            instance = item.build(context)
            if not getattr(instance, "slug", None):
                instance.slug = slug
            return instance
        return item
    except UnknownConnectorError:
        available = ", ".join(sorted(source_registry.all())) or "(none)"
        raise UnknownConnectorError(
            f"Unknown source {slug!r}. Available: {available}. "
            'Declare kind = "jsonld" (or another generic base) under [sources.<slug>] for config-only connectors.'
        )


def _merge_options(
    *,
    source_config: dict[str, Any],
    provider_targets: dict[str, Any],
    detail_limit: int,
    max_pages: int,
    board_tokens: list[str] | None,
    max_boards: int | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for key, value in {**provider_targets, **source_config}.items():
        if key in {"kind", "role_lane"}:
            continue
        options[key] = value
    options["detail_limit"] = detail_limit
    options["max_pages"] = max_pages
    if max_boards is not None:
        options["max_boards"] = max_boards
    tokens = board_tokens
    if tokens is None:
        tokens = source_config.get("board_tokens") or provider_targets.get("manual_board_tokens")
    if tokens is not None:
        options["board_tokens"] = list(tokens)
    # HTML docs use list_selector; code uses link_selector
    if "list_selector" in options and "link_selector" not in options:
        options["link_selector"] = options["list_selector"]
    return options


def collect_provider_run(
    provider_slug: str,
    *,
    conn: Any | None = None,
    dry_run: bool,
    payload_out: str | Path | None = None,
    fixture_dir: str | Path | None = None,
    targets_path: str | Path | None = None,
    config_path: str | Path | None = None,
    run_key: str | None = None,
    now: datetime | None = None,
    max_pages: int = 1,
    detail_limit: int | None = None,
    board_tokens: list[str] | None = None,
    max_boards: int | None = None,
    root: str | Path | None = None,
    store: JobStore | None = None,
) -> CollectionResult:
    provider_slug = slugify(provider_slug)
    project_root = Path(root) if root else None
    targets = _load_targets(targets_path, root=project_root, fixture_mode=fixture_dir is not None)
    connectors = _load_jobsearch_sources(config_path=config_path, root=project_root)
    source_config = dict(connectors.get(provider_slug) or {})
    metrics = FetchMetrics()
    started_at = now or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    provider_targets = dict(targets.get("providers", {}).get(provider_slug) or {})
    if provider_targets.get("kind") and not source_config.get("kind"):
        source_config = {**provider_targets, **source_config}
    resolved_detail_limit = (
        detail_limit
        if detail_limit is not None
        else int(source_config.get("detail_limit") or provider_targets.get("default_detail_limit") or 10)
    )
    resolved_max_boards = (
        max_boards
        if max_boards is not None
        else int(
            source_config.get("max_boards")
            or (targets.get("providers", {}).get("greenhouse") or {}).get("default_max_boards")
            or provider_targets.get("default_max_boards")
            or 10
        )
    )
    fetcher = FixtureFetcher(fixture_dir, metrics) if fixture_dir else LiveFetcher(metrics)
    source = resolve_source(
        provider_slug,
        source_config=source_config,
        provider_targets=provider_targets,
        root=project_root,
    )
    role_lane = source_config.get("role_lane") or targets.get("role_lane") or {}
    merged_targets = dict(targets)
    merged_targets["role_lane"] = role_lane
    providers = dict(merged_targets.get("providers") or {})
    providers[provider_slug] = {
        **provider_targets,
        **{k: v for k, v in source_config.items() if k != "role_lane"},
    }
    merged_targets["providers"] = providers
    options = _merge_options(
        source_config=source_config,
        provider_targets=provider_targets,
        detail_limit=resolved_detail_limit,
        max_pages=max_pages,
        board_tokens=board_tokens,
        max_boards=resolved_max_boards,
    )
    ctx = CollectionContext(
        conn=conn,
        fetcher=fetcher,
        targets=merged_targets,
        metrics=metrics,
        provider_slug=provider_slug,
        options=options,
    )
    try:
        candidates, status, blockers = source.discover(ctx)
    finally:
        fetcher.close()

    finished_at = now or utc_now()
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    run_key = normalize_space(run_key) or f"{provider_slug}-discovery-{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    lane_name = normalize_space((role_lane or {}).get("name")) or "target"
    summary = (
        f"{provider_slug} discovered {metrics.jobs_discovered} {lane_name} jobs; "
        f"emitted {len(candidates)}, skipped {metrics.jobs_skipped_as_duplicates} duplicates, "
        f"{metrics.request_count} requests."
    )
    if blockers:
        summary += f" Blockers: {' | '.join(blockers)}"
    payload = _build_payload(
        provider_slug, run_key, started_at, finished_at, status, summary, blockers, metrics, candidates
    )
    metrics.payload_size_bytes = len(_json(payload).encode("utf-8"))
    payload["run"]["metrics"] = metrics.to_dict(status)
    output_path = _payload_path(
        provider_slug, run_key, payload_out if dry_run and payload_out else payload_out
    )
    if not dry_run or payload_out:
        output_path = _write_payload(output_path, payload)
    else:
        output_path = None

    persisted = False
    persisted_result = None
    if not dry_run:
        if not output_path:
            output_path = _write_payload(_payload_path(provider_slug, run_key, None), payload)
        if store is not None:
            result = store.upsert_run_payload(provider_slug, str(output_path))
            persisted_result = vars(result)
        else:
            persisted_result = upsert_run_payload(conn, provider_slug, output_path)
        persisted = True

    return CollectionResult(
        provider_slug=provider_slug,
        candidates=candidates,
        status=status,
        summary=summary,
        blockers=blockers,
        metrics=metrics,
        run_key=run_key,
        payload=payload,
        payload_path=output_path,
        persisted=persisted,
        persisted_result=persisted_result,
    )


def benchmark_providers(
    providers: list[str],
    *,
    live: bool,
    fixture_dir: str | Path | None = None,
    now: datetime | None = None,
    max_pages: int = 1,
    detail_limit: int = 2,
    max_boards: int = 2,
) -> dict[str, Any]:
    results = []
    for provider in providers:
        try:
            result = collect_provider_run(
                provider,
                conn=None,
                dry_run=True,
                payload_out=None,
                fixture_dir=None if live else fixture_dir or FIXTURE_ROOT,
                now=now,
                max_pages=max_pages,
                detail_limit=detail_limit,
                max_boards=max_boards,
            )
            results.append(result.to_dict(dry_run=True))
        except Exception as exc:
            results.append(
                {
                    "provider": slugify(provider),
                    "dry_run": True,
                    "status": "partial",
                    "summary": f"{provider} benchmark failed: {exc}",
                    "run_key": None,
                    "payload_path": None,
                    "opportunities": 0,
                    "source_items": 0,
                    "blockers": [str(exc)],
                    "metrics": {"run_status": "partial"},
                    "persisted": False,
                    "persisted_result": None,
                }
            )
    return {"mode": "live" if live else "fixture", "results": results}


def _load_source_entry_point(entry_point: Any) -> ConnectorSpec:
    return ConnectorSpec(slug=entry_point.name, loaded=entry_point.load())


def _register_builtin_sources() -> None:
    from jobtracker.sources.services import ashby, djinni, dou, greenhouse, lever, workua  # noqa: F401


_register_builtin_sources()
source_registry.load_entry_points("jobtracker.sources", entry_point_loader=_load_source_entry_point)

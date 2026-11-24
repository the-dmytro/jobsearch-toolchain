"""Collect facts about the current environment before choosing how to set it up.

``jobtracker probe-environment`` reports what this process can reach and what the
repository already declares. It never changes anything, never prints secret values,
and never picks an option: it lists candidates with evidence so an agent can propose
choices to the user. Agent-side tools (for example MCP connectors) are invisible to
Python; the agent adds them from its own tool list.
"""

from __future__ import annotations

import os
import platform
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .app_config.loader import DEFAULT_CONFIG_PATH, STORE_CONNECTOR_ENV, load_app_config
from .config import load_env_file, load_settings
from .store.connectors import list_connectors

PROBE_SCHEMA = "jobtracker-environment-probe/v1"
SETUP_NOTES_PATH = Path("config/setup-notes.md")
SUPABASE_HOST_MARKERS = (".supabase.co", ".supabase.com")


def _runtime() -> dict[str, Any]:
    """Capabilities of this process. No platform is identified: environments are open-ended."""
    proxy_names = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy")
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "psycopg_installed": _has_module("psycopg"),
        "proxy_variables": sorted(name for name in proxy_names if os.getenv(name)),
        "in_container": Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
    }


def _tcp(host: str, port: int, timeout: float) -> dict[str, Any]:
    entry: dict[str, Any] = {"host": host, "port": port}
    try:
        families = {info[0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        entry["ipv4"] = socket.AF_INET in families
        entry["ipv6"] = socket.AF_INET6 in families
    except OSError as exc:
        entry["result"] = f"dns_failed: {exc}"
        return entry
    try:
        with socket.create_connection((host, port), timeout=timeout):
            entry["result"] = "open"
    except OSError as exc:
        entry["result"] = f"{type(exc).__name__}: {exc}"
    return entry


def _https(url: str, timeout: float) -> dict[str, Any]:
    entry: dict[str, Any] = {"url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout) as response:
            entry["result"] = f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        entry["result"] = f"http_{exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        entry["result"] = f"failed: {getattr(exc, 'reason', exc)}"
    return entry


def _supabase_evidence(store: dict[str, Any]) -> list[str]:
    """Explicit signs that the database is hosted on Supabase. Postgres alone is not one."""
    evidence: list[str] = []
    if (store.get("hosting") or "").lower() == "supabase":
        evidence.append('store.hosting = "supabase"')
    if os.getenv("SUPABASE_URL"):
        evidence.append("SUPABASE_URL is set")
    db_url = load_settings().db_url or ""
    host = urlparse(db_url).hostname or ""
    if host.endswith(SUPABASE_HOST_MARKERS):
        evidence.append("JOBTRACKER_DATABASE_URL points at a Supabase host")
    return evidence


def _repository(root: Path) -> dict[str, Any]:
    config_path = root / DEFAULT_CONFIG_PATH
    info: dict[str, Any] = {
        "config": config_path.exists(),
        "connector_variable": STORE_CONNECTOR_ENV,
        "selected_connector": (os.getenv(STORE_CONNECTOR_ENV) or "").strip().lower() or None,
        "setup_notes": (root / SETUP_NOTES_PATH).exists(),
        "provider_targets": (root / "profile/provider_targets.toml").exists(),
        "profile_files": sorted(path.name for path in (root / "profile").glob("*.md"))
        if (root / "profile").is_dir()
        else [],
    }
    info["setup_state"] = "existing" if info["config"] and info["provider_targets"] else "new"
    store: dict[str, Any] = {}
    sources: list[str] = []
    if info["config"]:
        try:
            config = load_app_config(root=root)
            store = {key: config.store.get(key) for key in ("backend", "connector", "hosting")}
            for source in config.source_configs.values():
                for key in ("listing_url", "url", "feed_url", "base_url"):
                    value = source.get(key)
                    if isinstance(value, str) and value.startswith("http"):
                        sources.append(value)
            info["mail"] = {
                key: (value or {}).get("kind")
                for key, value in config.mail.items()
                if key in {"inbox", "outbox"}
            }
        except Exception as exc:
            info["config_error"] = str(exc)
            try:
                from .app_config.loader import tomllib

                raw = tomllib.loads(config_path.read_text(encoding="utf-8")).get("store") or {}
                store = {key: raw.get(key) for key in ("backend", "hosting")}
                store["connector"] = (os.getenv(STORE_CONNECTOR_ENV) or "").strip().lower() or None
            except Exception:
                store = {}
    info["store"] = store
    info["source_urls"] = sorted(set(sources))
    return info


def probe_environment(root: Path, *, timeout: float = 5.0) -> dict[str, Any]:
    load_env_file(root / ".env")
    repository = _repository(root)
    store = repository.get("store") or {}
    supabase_evidence = _supabase_evidence(store)

    candidates: list[dict[str, Any]] = []
    for connector in list_connectors():
        info = connector.info
        entry: dict[str, Any] = {"connector": info.name, **info.as_dict()}
        declared = (store.get("hosting") or "").lower()
        has_evidence = (
            info.hosting == "any"
            or declared == info.hosting
            or (info.hosting == "supabase" and bool(supabase_evidence))
        )
        if not has_evidence:
            entry["status"] = "not_applicable"
            entry["evidence"] = [
                f"no explicit sign that the database is hosted on {info.hosting}; ask the user where it is hosted"
            ]
            entry["needs"] = []
        else:
            result = connector.probe(store, timeout=timeout).as_dict()
            entry.update({key: result[key] for key in ("status", "evidence", "needs")})
            if info.hosting == "supabase":
                entry["evidence"] = supabase_evidence + entry["evidence"]
        entry["selected"] = (repository.get("selected_connector") or store.get("connector")) == info.name
        candidates.append(entry)

    network: dict[str, Any] = {
        "https": [_https(url, timeout) for url in repository.get("source_urls", [])[:20]],
    }
    mail_hosts = []
    for name, port in (
        ("JOBTRACKER_IMAP_HOST", 993),
        ("JOBTRACKER_SMTP_HOST", int(os.getenv("JOBTRACKER_SMTP_PORT") or 465)),
    ):
        host = (os.getenv(name) or "").strip()
        if host:
            mail_hosts.append(_tcp(host, port, timeout))
    network["mail_tcp"] = mail_hosts

    return {
        "schema": PROBE_SCHEMA,
        "runtime": _runtime(),
        "repository": repository,
        "database": {
            "declared_backend": store.get("backend"),
            "declared_hosting": store.get("hosting"),
            "supabase_evidence": supabase_evidence,
            "candidates": candidates,
        },
        "network": network,
        "not_visible_here": [
            "agent-side tools such as MCP connectors (check the agent's own tool list)",
            "the platform's environment controls (network policy, variables, secrets, setup script)",
            "facts only the user knows: where the database is hosted, which credentials exist",
            f"earlier findings recorded in {SETUP_NOTES_PATH} (read it)",
        ],
    }


def _has_module(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def format_probe(probe: dict[str, Any]) -> str:
    repo = probe["repository"]
    runtime = probe["runtime"]
    store = repo.get("store") or {}
    lines = [
        f"runtime:     {runtime['os']} python {runtime['python']}  proxy variables: "
        f"{', '.join(runtime['proxy_variables']) or 'none'}",
        f"setup state: {repo['setup_state']}  setup notes: {'yes' if repo['setup_notes'] else 'no'}",
        f"store:       backend={store.get('backend')} hosting={store.get('hosting')} "
        f"connector={repo['selected_connector'] or '(' + repo['connector_variable'] + ' not set)'}",
    ]
    if repo.get("config_error"):
        lines.append(f"config:      {repo['config_error']}")
    lines.append("connectors:")
    for item in probe["database"]["candidates"]:
        mark = "*" if item["selected"] else " "
        lines.append(f"  {mark} {item['connector']:<16} {item['status']:<15} network={item['network']}")
        for evidence in item["evidence"]:
            lines.append(f"        - {evidence}")
        for need in item["needs"]:
            lines.append(f"        needs: {need}")
    lines.append("not visible to this probe: " + "; ".join(probe["not_visible_here"]))
    return "\n".join(lines)

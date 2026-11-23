"""Supabase-hosted PostgreSQL over HTTPS (Data API RPC gateway from migration 008)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ...config import load_env_file
from ..https_sql import RPC_PATH, connect_https
from .base import ConnectorInfo, ProbeResult


class SupabaseHttpsConnector:
    info = ConnectorInfo(
        name="supabase_https",
        dialect="postgres",
        network="https",
        hosting="supabase",
        transactional=False,
        settings=("SUPABASE_URL", "SUPABASE_SECRET_KEY"),
        secrets=("SUPABASE_SECRET_KEY",),
        description=(
            "Supabase project over HTTPS (Data API). Works behind HTTP-only proxies. "
            "Each statement commits on its own; writes are idempotent and read back."
        ),
    )

    @contextmanager
    def connect(self, options: dict[str, Any]) -> Iterator[Any]:
        with connect_https() as conn:
            yield conn

    def target(self, options: dict[str, Any]) -> str:
        load_env_file()
        url = (os.getenv("SUPABASE_URL") or "").strip()
        return url.split("://", 1)[-1].split("/", 1)[0] if url else "unconfigured"

    def probe(self, options: dict[str, Any], *, timeout: float) -> ProbeResult:
        load_env_file()
        result = ProbeResult(self.info.name, "not_configured")
        url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
        key = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not url:
            result.needs.append("SUPABASE_URL (https://<project-ref>.supabase.co)")
            return result
        result.evidence.append(f"target {self.target(options)}")
        request = urllib.request.Request(
            url + RPC_PATH,
            data=json.dumps({"query": "select 1 as ok", "mode": "rows"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json", **({"apikey": key} if key else {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                result.status = "available"
                result.evidence.append("gateway query succeeded")
        except urllib.error.HTTPError as exc:
            result.status = "reachable"
            result.evidence.append(f"HTTPS endpoint answered {exc.code}")
            if exc.code in {401, 403}:
                result.needs.append(
                    "SUPABASE_SECRET_KEY (secret or service_role key; set to proxy-injected when a network "
                    "secret supplies it)"
                )
            elif exc.code == 404:
                result.needs.append("migration 008_https_sql_gateway.sql applied in the Supabase SQL editor")
            else:
                result.needs.append("see the HTTP error above")
        except (urllib.error.URLError, OSError) as exc:
            result.status = "blocked"
            result.evidence.append(f"HTTPS request failed: {exc}")
            result.needs.append(f"allow host {self.target(options)} in the environment's network policy")
        if (
            not key
            and result.status != "blocked"
            and not any("SUPABASE_SECRET_KEY" in item for item in result.needs)
        ):
            result.needs.append("SUPABASE_SECRET_KEY")
        return result

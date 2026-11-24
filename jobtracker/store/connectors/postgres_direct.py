"""Generic PostgreSQL over the wire protocol (psycopg). Works with any host."""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from ...config import load_settings
from ...db import _host_from_db_url, connect
from .base import ConnectorInfo, ProbeResult


class PostgresDirectConnector:
    info = ConnectorInfo(
        name="postgres_direct",
        dialect="postgres",
        network="postgres_wire",
        hosting="any",
        transactional=True,
        settings=("JOBTRACKER_DATABASE_URL",),
        secrets=("JOBTRACKER_DATABASE_URL",),
        description="PostgreSQL protocol via psycopg to any PostgreSQL host (self-hosted, Supabase, Neon, RDS, ...).",
    )

    @contextmanager
    def connect(self, options: dict[str, Any]) -> Iterator[Any]:
        with connect() as conn:
            yield conn

    def target(self, options: dict[str, Any]) -> str:
        return _host_from_db_url(load_settings().db_url) or "unconfigured"

    def probe(self, options: dict[str, Any], *, timeout: float) -> ProbeResult:
        url = load_settings().db_url
        result = ProbeResult(self.info.name, "not_configured")
        if not url:
            result.needs.append("JOBTRACKER_DATABASE_URL (connection string from the database provider)")
            return result
        parsed = urlparse(url)
        host, port = parsed.hostname or "", parsed.port or 5432
        result.evidence.append(f"target {host}:{port}")
        try:
            families = {info[0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except OSError as exc:
            result.status = "blocked"
            result.evidence.append(f"DNS lookup failed: {exc}")
            return result
        if socket.AF_INET not in families:
            result.evidence.append("host has no IPv4 address (IPv6 only)")
        try:
            with socket.create_connection((host, port), timeout=timeout):
                result.evidence.append("TCP connection succeeded")
        except OSError as exc:
            result.status = "blocked"
            result.evidence.append(f"TCP connection failed: {type(exc).__name__}: {exc}")
            if os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"):
                result.evidence.append("an HTTP(S) proxy is configured; this sandbox may allow only HTTP(S)")
            return result
        try:
            with self.connect(options) as conn, conn.cursor() as cur:
                cur.execute("select 1 as ok")
                cur.fetchone()
            result.status = "available"
            result.evidence.append("query succeeded")
        except Exception as exc:  # report, do not decide
            result.status = "reachable"
            result.evidence.append(f"login or query failed: {exc}")
            result.needs.append("valid JOBTRACKER_DATABASE_URL credentials")
        return result

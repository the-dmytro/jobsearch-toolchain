"""PostgreSQL over HTTPS through the Supabase Data API (migration 008).

Selected explicitly with ``[store] backend = "postgres"`` and
``transport = "supabase_https"``. It reaches the same database as the direct
PostgreSQL transport; it is never used as a fallback for it.

The connection mimics the small psycopg surface the toolchain uses: ``cursor()``
with ``execute``/``fetchone``/``fetchall``/``rowcount``, ``transaction()`` and
``commit()``. Each statement is one HTTPS request and commits on its own, so a
multi-statement operation is not atomic. Every toolchain write is idempotent and
read back, so a failed command exits non-zero and rerunning it completes the write.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from ..config import load_env_file
from ..db import MissingConfigurationError

RPC_PATH = "/rest/v1/rpc/jobtracker_sql"
KEY_ENV_NAMES = ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
DEFAULT_TIMEOUT_SECONDS = 60.0

_LEADING_NOISE = re.compile(r"^(\s+|--[^\n]*\n|/\*.*?\*/)+", re.DOTALL)
_RETURNING = re.compile(r"\breturning\b", re.IGNORECASE)


class HttpsSqlError(RuntimeError):
    """The database rejected a statement sent over HTTPS."""


def render_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return f"'{value}'::float8"
        return repr(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return render_literal(value.isoformat())
    if isinstance(value, uuid.UUID):
        return render_literal(str(value))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"'\\x{bytes(value).hex()}'::bytea"
    if isinstance(value, (list, tuple)):
        if not value:
            return "'{}'"
        return "ARRAY[" + ", ".join(render_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        return render_literal(json.dumps(value, ensure_ascii=False))
    text = str(value)
    if "\x00" in text:
        raise ValueError("NUL characters cannot be sent to PostgreSQL")
    return "'" + text.replace("'", "''") + "'"


def render_query(query: str, params: tuple[Any, ...] | list[Any] | None) -> str:
    """Replace psycopg-style ``%s`` placeholders with SQL literals (outside quotes)."""
    if params is None:
        return query
    values = list(params)
    output: list[str] = []
    index = 0
    position = 0
    length = len(query)
    while position < length:
        char = query[position]
        if char == "'":
            end = position + 1
            while end < length:
                if query[end] == "'" and end + 1 < length and query[end + 1] == "'":
                    end += 2
                    continue
                if query[end] == "'":
                    break
                end += 1
            output.append(query[position : end + 1])
            position = end + 1
            continue
        if char == "%" and position + 1 < length:
            following = query[position + 1]
            if following == "s":
                if index >= len(values):
                    raise ValueError("Not enough parameters for query")
                output.append(render_literal(values[index]))
                index += 1
                position += 2
                continue
            if following == "%":
                output.append("%")
                position += 2
                continue
        output.append(char)
        position += 1
    if index != len(values):
        raise ValueError(f"Query used {index} parameters but {len(values)} were given")
    return "".join(output)


def statement_mode(query: str) -> str:
    head = _LEADING_NOISE.sub("", query).lstrip("(").lower()
    first = head.split(None, 1)[0] if head.split() else ""
    if first in {"select", "with", "values", "table", "show"}:
        return "rows"
    if first in {"insert", "update", "delete", "merge"} and _RETURNING.search(query):
        return "rows"
    return "exec"


class HttpsCursor:
    def __init__(self, connection: HttpsConnection) -> None:
        self.connection = connection
        self._rows: list[dict[str, Any]] = []
        self.rowcount = -1

    def __enter__(self) -> HttpsCursor:
        return self

    def __exit__(self, *exc: Any) -> None:
        self._rows = []

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> HttpsCursor:
        sql = render_query(query, params).strip().rstrip(";")
        mode = statement_mode(sql)
        result = self.connection.rpc(sql, mode)
        rows = result.get("rows") if isinstance(result, dict) else None
        self._rows = list(rows) if isinstance(rows, list) else []
        self.rowcount = int(result.get("rowcount", len(self._rows))) if isinstance(result, dict) else -1
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        rows, self._rows = self._rows, []
        return rows


class HttpsConnection:
    transport = "supabase_https"

    def __init__(self, base_url: str, api_key: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.requests = 0

    @property
    def host(self) -> str:
        return re.sub(r"^https?://", "", self.base_url).split("/", 1)[0]

    def cursor(self) -> HttpsCursor:
        return HttpsCursor(self)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        # Statements commit individually over HTTPS; see the module docstring.
        yield

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def rpc(self, query: str, mode: str) -> Any:
        body = json.dumps({"query": query, "mode": mode}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + RPC_PATH,
            data=body,
            method="POST",
            headers={
                "apikey": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self.requests += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
            except ValueError:
                payload = {"message": detail[:500]}
            message = payload.get("message") or detail[:500]
            if exc.code == 404 or payload.get("code") == "PGRST202":
                raise MissingConfigurationError(
                    f"{self.host} has no jobtracker_sql function. Apply db/migrations/008_https_sql_gateway.sql "
                    "once over a direct connection or in the Supabase SQL editor."
                ) from exc
            if exc.code in {401, 403}:
                raise MissingConfigurationError(
                    f"{self.host} rejected the API key ({exc.code}): {message}. Use the project's secret "
                    "(service_role) key in SUPABASE_SECRET_KEY or the environment's network secret."
                ) from exc
            raise HttpsSqlError(f"{message} [{payload.get('code') or exc.code}]") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MissingConfigurationError(f"Cannot reach {self.host} over HTTPS: {exc}") from exc


def https_settings() -> tuple[str, str]:
    load_env_file()
    base_url = (os.getenv("SUPABASE_URL") or "").strip()
    if not base_url.startswith("https://"):
        raise MissingConfigurationError(
            'SUPABASE_URL (https://<project-ref>.supabase.co) is required for store.transport = "supabase_https".'
        )
    for name in KEY_ENV_NAMES:
        key = (os.getenv(name) or "").strip()
        if key:
            return base_url, key
    raise MissingConfigurationError(
        'SUPABASE_SECRET_KEY is required for store.transport = "supabase_https". When a proxy injects '
        "the key as a network secret, set SUPABASE_SECRET_KEY=proxy-injected."
    )


@contextmanager
def connect_https() -> Iterator[HttpsConnection]:
    base_url, key = https_settings()
    yield HttpsConnection(base_url, key)

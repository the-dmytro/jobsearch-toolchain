from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jobtracker.db import MissingDependencyError
from jobtracker.utils import normalize_space

USER_AGENT = "JobSearchTracker/0.1 (+https://github.com/example/jobsearch-toolchain)"
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "provider_fetch"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_RETRIES = 2

_WORKUA_JOB_RE = re.compile(r"/jobs/(\d+)/")
_GREENHOUSE_API_RE = re.compile(r"/boards/([^/]+)/jobs", re.IGNORECASE)


def _require_httpx():
    try:
        import httpx
    except ImportError as exc:
        raise MissingDependencyError(
            "httpx is required for live provider collectors. Install dependencies with `python3 -m pip install -r requirements.txt`."
        ) from exc
    return httpx


class LiveFetcher:
    def __init__(self, metrics: Any, timeout: float = DEFAULT_TIMEOUT_SECONDS, retries: int = DEFAULT_RETRIES) -> None:
        httpx = _require_httpx()
        self._httpx = httpx
        self._metrics = metrics
        self._retries = retries
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def get_text(self, url: str, kind: str) -> str:
        return self._request(url, kind).text

    def get_json(self, url: str, kind: str) -> Any:
        return self._request(url, kind).json()

    def close(self) -> None:
        self._client.close()

    def _request(self, url: str, kind: str):
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            started = time.perf_counter()
            try:
                response = self._client.get(url)
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._metrics.record_request(kind, latency_ms, retried=attempt > 0)
                response.raise_for_status()
                return response
            except self._httpx.HTTPError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._metrics.record_request(kind, latency_ms, retried=attempt > 0)
                last_error = exc
                retriable = isinstance(exc, self._httpx.TransportError)
                response = getattr(exc, "response", None)
                if response is not None and response.status_code >= 500:
                    retriable = True
                if not retriable or attempt == self._retries:
                    break
        raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


class FixtureFetcher:
    def __init__(self, fixture_dir: str | Path | None, metrics: Any) -> None:
        self._fixture_dir = Path(fixture_dir) if fixture_dir else FIXTURE_ROOT
        self._metrics = metrics

    def close(self) -> None:
        return None

    def get_text(self, url: str, kind: str) -> str:
        path = self._fixture_path(url)
        started = time.perf_counter()
        content = path.read_text(encoding="utf-8")
        self._metrics.record_request(kind, int((time.perf_counter() - started) * 1000))
        return content

    def get_json(self, url: str, kind: str) -> Any:
        return json.loads(self.get_text(url, kind))

    def _fixture_path(self, url: str) -> Path:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path
        if "jobs.dou.ua" in host and "/feeds/" in path:
            return self._fixture_dir / "dou_feed.xml"
        if "jobs.dou.ua" in host and "/vacancies/" in path and "feeds" not in path and "companies" not in path:
            return self._fixture_dir / "dou_list.html"
        if "jobs.dou.ua" in host and "/companies/" in path and "/vacancies/" in path:
            return self._fixture_dir / "dou_detail.html"
        if "work.ua" in host and re.fullmatch(r"/jobs-[^/]+/?", path):
            return self._fixture_dir / "workua_list.html"
        if "work.ua" in host and _WORKUA_JOB_RE.search(path):
            return self._fixture_dir / "workua_detail.html"
        if "djinni.co" in host and "/jobs/keyword-" in path:
            return self._fixture_dir / "djinni_list.html"
        if "djinni.co" in host and "/jobs/" in path:
            return self._fixture_dir / "djinni_detail.html"
        if "boards-api.greenhouse.io" in host:
            match = _GREENHOUSE_API_RE.search(path)
            token = normalize_space(match.group(1) if match else "default").lower()
            return self._fixture_dir / f"greenhouse_{token}.json"
        if "api.lever.co" in host:
            return self._fixture_dir / "lever_default.json"
        if "api.ashbyhq.com" in host:
            return self._fixture_dir / "ashby_default.json"
        raise FileNotFoundError(f"No fixture mapped for {url}")

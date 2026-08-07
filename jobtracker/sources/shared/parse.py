from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from jobtracker.db import MissingDependencyError
from jobtracker.utils import normalize_name, normalize_space


def _text_from_html(value: str | None) -> str:
    html = value or ""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return normalize_space(unescape(re.sub(r"<[^>]+>", " ", html)))
    return normalize_space(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise MissingDependencyError(
            "beautifulsoup4 is required for provider collectors. Install dependencies with `python3 -m pip install -r requirements.txt`."
        ) from exc
    return BeautifulSoup(html, "html.parser")


def _parse_json_ld_jobs(html_text: str) -> list[dict[str, Any]]:
    soup = _soup(html_text)
    jobs: list[dict[str, Any]] = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = normalize_space(node.string or node.get_text())
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                jobs.append(item)
    return jobs


def _first_link_text_from_html(value: str | None) -> str | None:
    html = value or ""
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        match = re.search(r"<a\b[^>]*>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL)
        return normalize_space(unescape(re.sub(r"<[^>]+>", " ", match.group(1)))) if match else None
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a"):
        text = normalize_space(anchor.get_text(" ", strip=True))
        href = normalize_space(anchor.get("href"))
        lowered = normalize_name(text)
        if not text or "відгук" in lowered or "apply" in lowered or "#reply" in href:
            continue
        return text
    return None

from __future__ import annotations

from typing import Any

import httpx

from ..base import RunReport


class WebhookNotifier:
    slug = "webhook"

    def __init__(self, *, url: str, timeout_seconds: float = 30.0) -> None:
        self.url = url.strip()
        self.timeout_seconds = timeout_seconds

    def notify(self, report: RunReport) -> dict[str, Any]:
        payload = report.to_dict()
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.url, json=payload)
            response.raise_for_status()
        return {
            "sent": True,
            "url": self.url,
            "status_code": response.status_code,
        }

    def health(self) -> list[str]:
        if not self.url:
            return ["webhook notifier: url is required"]
        if self.url.startswith("{{") and self.url.endswith("}}"):
            return [f"webhook notifier: unresolved placeholder in url ({self.url})"]
        return []

from __future__ import annotations

from typing import Any

import httpx

from ..base import RunReport


class SlackNotifier:
    slug = "slack"

    def __init__(self, *, webhook_url: str, timeout_seconds: float = 30.0) -> None:
        self.webhook_url = webhook_url.strip()
        self.timeout_seconds = timeout_seconds

    def notify(self, report: RunReport) -> dict[str, Any]:
        text = report.body or report.summary
        subject = report.subject or report.run_key
        payload = {
            "text": f"*{subject}*\n{text}",
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{subject}*\n{text}"},
                }
            ],
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.webhook_url, json=payload)
            response.raise_for_status()
        return {"sent": True, "status_code": response.status_code}

    def health(self) -> list[str]:
        if not self.webhook_url:
            return ["slack notifier: webhook_url is required"]
        if self.webhook_url.startswith("{{") and self.webhook_url.endswith("}}"):
            return [f"slack notifier: unresolved placeholder in webhook_url ({self.webhook_url})"]
        return []

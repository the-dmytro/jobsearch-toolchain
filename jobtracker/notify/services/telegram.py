from __future__ import annotations

from typing import Any

import httpx

from ..base import RunReport


class TelegramNotifier:
    slug = "telegram"

    def __init__(self, *, bot_token: str, chat_id: str, timeout_seconds: float = 30.0) -> None:
        self.bot_token = bot_token.strip()
        self.chat_id = chat_id.strip()
        self.timeout_seconds = timeout_seconds

    @property
    def api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def notify(self, report: RunReport) -> dict[str, Any]:
        text = report.body or report.summary
        subject = report.subject or report.run_key
        message = f"{subject}\n\n{text}"
        payload = {"chat_id": self.chat_id, "text": message}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.api_url, json=payload)
            response.raise_for_status()
        return {"sent": True, "status_code": response.status_code}

    def health(self) -> list[str]:
        issues: list[str] = []
        if not self.bot_token:
            issues.append("telegram notifier: bot_token is required")
        elif self.bot_token.startswith("{{") and self.bot_token.endswith("}}"):
            issues.append(f"telegram notifier: unresolved placeholder in bot_token ({self.bot_token})")
        if not self.chat_id:
            issues.append("telegram notifier: chat_id is required")
        elif self.chat_id.startswith("{{") and self.chat_id.endswith("}}"):
            issues.append(f"telegram notifier: unresolved placeholder in chat_id ({self.chat_id})")
        return issues

from __future__ import annotations

from typing import Any

from ...mail.base import OutgoingMessage
from ...mail.generic.smtp import SmtpMailSender
from ..base import RunReport


class EmailNotifier:
    slug = "email"

    def __init__(
        self,
        *,
        to: str,
        subject_template: str = "{subject}",
        from_address: str | None = None,
    ) -> None:
        self.to = to.strip()
        self.subject_template = subject_template
        self.from_address = from_address

    def notify(self, report: RunReport) -> dict[str, Any]:
        subject = self.subject_template.format(
            subject=report.subject or report.summary,
            run_key=report.run_key,
            status=report.status,
            pipeline=report.pipeline,
            summary=report.summary,
        )
        body = report.body or report.summary
        sender = SmtpMailSender(sender=self.from_address)
        from_addr = self.from_address or sender.default_sender
        receipt = sender.send(
            OutgoingMessage(
                sender=from_addr or sender.default_sender,
                recipient=self.to,
                subject=subject,
                body=body,
            )
        )
        return {"sent": receipt.sent, "recipient": receipt.recipient, "subject": receipt.subject}

    def health(self) -> list[str]:
        issues: list[str] = []
        if not self.to:
            issues.append("email notifier: recipient (to) is required")
        try:
            SmtpMailSender(sender=self.from_address)
        except Exception as exc:
            issues.append(f"email notifier: SMTP configuration unavailable ({exc})")
        return issues

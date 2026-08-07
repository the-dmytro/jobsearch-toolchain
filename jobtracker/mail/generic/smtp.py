from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from ...config import load_env_file
from ..base import MailSender, OutgoingMessage, SendReceipt


def _smtp_setting(name: str, default: str | None = None) -> str | None:
    return os.getenv(f"JOBTRACKER_{name}") or os.getenv(name) or default


class SmtpMailSender:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        sender: str | None = None,
    ) -> None:
        load_env_file()
        self.host = host or _smtp_setting("SMTP_HOST")
        self.port = port if port is not None else int(_smtp_setting("SMTP_PORT", "465") or "465")
        self.user = user or _smtp_setting("SMTP_USER")
        self.password = password or _smtp_setting("SMTP_PASSWORD")
        self.default_sender = sender or _smtp_setting("SMTP_FROM") or self.user
        if not self.host or not self.default_sender or not self.user or not self.password:
            raise RuntimeError(
                "JOBTRACKER_SMTP_HOST, JOBTRACKER_SMTP_USER, JOBTRACKER_SMTP_PASSWORD, and JOBTRACKER_SMTP_FROM are required."
            )

    def send(self, message: OutgoingMessage) -> SendReceipt:
        recipient = (message.recipient or "").strip()
        if not recipient:
            raise ValueError("recipient is required for SMTP send")
        sender = message.sender or self.default_sender
        email_message = EmailMessage()
        email_message["From"] = sender
        email_message["To"] = recipient
        email_message["Subject"] = message.subject
        email_message.set_content(message.body)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.host, self.port, context=context) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(email_message)
        return SendReceipt(sent=True, recipient=recipient, subject=message.subject)

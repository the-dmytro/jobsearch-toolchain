"""Send an iTIP REPLY by SMTP. Sending is a message on the user's behalf: callers must confirm."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from typing import Any

SmtpFactory = Callable[[str, int], Any]


def _smtp_value(options: Mapping[str, Any], env: Mapping[str, str], key: str, name: str) -> str:
    value = options.get(key)
    if value not in (None, ""):
        return str(value)
    return env.get(f"JOBTRACKER_{name}") or env.get(name) or ""


def build_reply_message(ics: str, to: str, subject: str, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = sender, to, subject
    message.set_content(subject)
    message.add_alternative(ics, subtype="calendar", params={"method": "REPLY"})
    return message


def send_reply(
    ics: str,
    to: str,
    subject: str,
    attendee: str,
    *,
    outbox: Mapping[str, Any],
    env: Mapping[str, str],
    smtp_factory: SmtpFactory | None = None,
) -> dict[str, Any]:
    host = _smtp_value(outbox, env, "host", "SMTP_HOST")
    port = int(_smtp_value(outbox, env, "port", "SMTP_PORT") or 465)
    user = _smtp_value(outbox, env, "user", "SMTP_USER")
    password = env.get("JOBTRACKER_SMTP_PASSWORD") or env.get("SMTP_PASSWORD") or ""
    sender = _smtp_value(outbox, env, "from_address", "SMTP_FROM") or attendee
    if not host or not user or not password:
        raise RuntimeError(
            "JOBTRACKER_SMTP_HOST, JOBTRACKER_SMTP_USER and JOBTRACKER_SMTP_PASSWORD are required to send"
        )
    message = build_reply_message(ics, to, subject, sender)
    context = ssl.create_default_context()
    if smtp_factory is None:
        if port == 465:
            client = smtplib.SMTP_SSL(host, port, context=context, timeout=60)
        else:
            client = smtplib.SMTP(host, port, timeout=60)
    else:
        client = smtp_factory(host, port)
    with client as smtp:
        if port != 465:
            smtp.starttls(context=context)
        smtp.login(user, password)
        smtp.send_message(message)
    return {"result": "sent", "to": to, "subject": subject}

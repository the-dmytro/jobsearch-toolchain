from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RawMessage:
    source_type: str = "email"
    message_id: str | None = None
    external_id: str | None = None
    subject: str | None = None
    sender: str | None = None
    recipient: str | None = None
    email_date: str | None = None
    timestamp: str | None = None
    text: str | None = None
    raw_text: str | None = None
    links: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_type": self.source_type,
            "message_id": self.message_id,
            "external_id": self.external_id,
            "subject": self.subject,
            "from": self.sender,
            "to": self.recipient,
            "email_date": self.email_date,
            "timestamp": self.timestamp,
            "text": self.text,
            "raw_text": self.raw_text,
            "links": list(self.links),
        }
        if self.metadata:
            payload.update(self.metadata)
        return payload


@dataclass(frozen=True)
class OutgoingMessage:
    sender: str
    recipient: str
    subject: str
    body: str


@dataclass(frozen=True)
class SendReceipt:
    sent: bool
    recipient: str
    subject: str
    idempotency_key: str | None = None
    skipped: bool = False
    reason: str | None = None


class MailInbox(Protocol):
    def list_folders(self) -> list[str]: ...

    def resolve_folder(self, provider: str, explicit_folder: str | None = None) -> str: ...

    def fetch_messages(
        self,
        folder: str,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...


class MailSender(Protocol):
    def send(self, message: OutgoingMessage) -> SendReceipt: ...


class AlertParser(Protocol):
    def matches(self, message: dict[str, Any]) -> bool: ...

    def parse(self, message: dict[str, Any]) -> dict[str, Any] | None: ...

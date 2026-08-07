from __future__ import annotations

import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - exercised in minimal environments
    BeautifulSoup = None

from ..base import RawMessage
from ...utils import normalize_space


def _clean_message_id(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    return text.strip("<>")


def _message_date(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return text


def _iter_parts(message: Message, content_type: str) -> list[str]:
    values: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart() or part.get_content_type() != content_type:
                continue
            values.append(_decode_part(part))
    elif message.get_content_type() == content_type:
        values.append(_decode_part(message))
    return [value for value in values if value]


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    charset = part.get_content_charset() or "utf-8"
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


class _LinkAndTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.links.append(unescape(value))

    def handle_data(self, data: str) -> None:
        if data:
            self.text_parts.append(data)


def _parse_html(html: str) -> tuple[str, list[str]]:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        links = [unescape(normalize_space(tag.get("href"))) for tag in soup.find_all("a") if normalize_space(tag.get("href"))]
        return normalize_space(soup.get_text(" ")), links
    parser = _LinkAndTextParser()
    parser.feed(html)
    return normalize_space(" ".join(parser.text_parts)), parser.links


def _html_to_text(html: str) -> str:
    text, _links = _parse_html(html)
    return text


def _html_links(html: str) -> list[str]:
    _text, links = _parse_html(html)
    return links


def _text_links(text: str) -> list[str]:
    return [match.group(0).rstrip(").,]") for match in re.finditer(r"https?://[^\s<>\"]+", text)]


def parse_email_message(raw_message: bytes) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    plain_parts = _iter_parts(message, "text/plain")
    html_parts = _iter_parts(message, "text/html")
    text = normalize_space("\n".join(plain_parts)) or normalize_space(" ".join(_html_to_text(part) for part in html_parts))
    links: list[str] = []
    for html in html_parts:
        links.extend(_html_links(html))
    links.extend(_text_links(text))
    deduped_links = list(dict.fromkeys(link for link in links if link))
    return {
        "source_type": "email",
        "message_id": _clean_message_id(message.get("Message-ID")),
        "external_id": _clean_message_id(message.get("Message-ID")),
        "subject": normalize_space(message.get("Subject")),
        "from": normalize_space(message.get("From")),
        "to": normalize_space(message.get("To")),
        "email_date": _message_date(message.get("Date")),
        "timestamp": _message_date(message.get("Date")),
        "text": text,
        "raw_text": text,
        "links": deduped_links,
    }


def parse_email_file(path: str) -> dict[str, Any]:
    from pathlib import Path

    return parse_email_message(Path(path).read_bytes())


def raw_message_from_dict(message: dict[str, Any]) -> RawMessage:
    metadata = {
        key: value
        for key, value in message.items()
        if key not in {
            "source_type",
            "message_id",
            "external_id",
            "subject",
            "from",
            "to",
            "email_date",
            "timestamp",
            "text",
            "raw_text",
            "links",
        }
    }
    return RawMessage(
        source_type=str(message.get("source_type") or "email"),
        message_id=message.get("message_id"),
        external_id=message.get("external_id"),
        subject=message.get("subject"),
        sender=message.get("from"),
        recipient=message.get("to"),
        email_date=message.get("email_date"),
        timestamp=message.get("timestamp"),
        text=message.get("text"),
        raw_text=message.get("raw_text"),
        links=list(message.get("links") or []),
        metadata=metadata,
    )

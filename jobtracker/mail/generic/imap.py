from __future__ import annotations

import imaplib
import os
import re
from typing import Any

from ...config import load_env_file, load_settings
from ...utils import normalize_name, slugify
from .eml import parse_email_message


def _folder_key(value: str) -> str:
    return normalize_name(value.replace("\\", "/"))


def resolve_mail_folder(
    folders: list[str],
    provider: str,
    explicit_folder: str | None = None,
    folder_aliases: dict[str, list[str]] | None = None,
) -> str:
    aliases = folder_aliases or load_settings().mail_folder_aliases
    candidates = [explicit_folder] if explicit_folder else aliases.get(slugify(provider), [])
    folders_by_key = {_folder_key(folder): folder for folder in folders}
    for candidate in candidates:
        if not candidate:
            continue
        matched = folders_by_key.get(_folder_key(candidate))
        if matched:
            return matched
    checked = ", ".join(candidate for candidate in candidates if candidate)
    raise RuntimeError(f"No IMAP folder found for {provider}. Checked: {checked}")


def _first_message_bytes(items: list[Any]) -> bytes | None:
    for item in items:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


class MailImapClient:
    def __init__(self, host: str | None = None, user: str | None = None, password: str | None = None) -> None:
        load_env_file()
        self.host = (
            host or os.getenv("JOBTRACKER_IMAP_HOST") or os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
        )
        self.user = user or os.getenv("JOBTRACKER_IMAP_USER") or os.getenv("GMAIL_IMAP_USER")
        self.password = password or os.getenv("JOBTRACKER_IMAP_PASSWORD") or os.getenv("GMAIL_IMAP_PASSWORD")
        if not self.user or not self.password:
            raise RuntimeError(
                "JOBTRACKER_IMAP_USER and JOBTRACKER_IMAP_PASSWORD are required for IMAP access."
            )
        self._conn: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "MailImapClient":
        self._conn = imaplib.IMAP4_SSL(self.host)
        self._conn.login(self.user, self.password)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._conn:
            return
        try:
            self._conn.logout()
        finally:
            self._conn = None

    @property
    def conn(self) -> imaplib.IMAP4_SSL:
        if not self._conn:
            raise RuntimeError("MailImapClient must be used as a context manager.")
        return self._conn

    def list_folders(self) -> list[str]:
        status, data = self.conn.list()
        if status != "OK":
            raise RuntimeError(f"IMAP LIST failed: {status}")
        folders: list[str] = []
        for raw in data:
            if not raw:
                continue
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            match = re.search(r'"([^"]+)"$', text)
            if match:
                folders.append(match.group(1))
        return sorted(folders)

    def list_labels(self) -> list[str]:
        return self.list_folders()

    def resolve_folder(self, provider: str, explicit_folder: str | None = None) -> str:
        return resolve_mail_folder(self.list_folders(), provider, explicit_folder=explicit_folder)

    def resolve_label(self, provider: str, explicit_label: str | None = None) -> str:
        return self.resolve_folder(provider, explicit_folder=explicit_label)

    def fetch_label_messages(
        self, label: str, since: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        return self.fetch_messages(label, since=since, limit=limit)

    def fetch_messages(
        self, folder: str, since: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        self.conn.select(f'"{folder}"', readonly=True)
        criteria = ["ALL"]
        if since:
            criteria = ["SINCE", since]
        status, data = self.conn.uid("search", None, *criteria)
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {status}")
        uids = (data[0] or b"").split()
        if limit is not None:
            uids = uids[-limit:]
        messages: list[dict[str, Any]] = []
        for uid in uids:
            raw = self._fetch_message_bytes(uid)
            if not raw:
                continue
            parsed = parse_email_message(raw)
            parsed["imap_uid"] = uid.decode("ascii", errors="replace")
            parsed["label"] = folder
            if not parsed.get("external_id"):
                parsed["external_id"] = f"{folder}:{parsed['imap_uid']}"
            messages.append(parsed)
        return messages

    def _fetch_message_bytes(self, uid: bytes) -> bytes | None:
        for fetch_spec in ("(BODY.PEEK[])", "(RFC822)"):
            status, fetched = self.conn.uid("fetch", uid, fetch_spec)
            if status != "OK":
                continue
            raw = _first_message_bytes(fetched)
            if raw:
                return raw
        return None


GmailImapClient = MailImapClient


class ImapMailInbox(MailImapClient):
    """Alias implementing MailInbox via MailImapClient."""

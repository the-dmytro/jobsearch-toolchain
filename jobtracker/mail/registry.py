from __future__ import annotations

from typing import Any

from ..config import load_settings
from ..utils import slugify
from .base import AlertParser, MailInbox
from .generic.imap import ImapMailInbox, MailImapClient, resolve_mail_folder
from .generic.maildir import MaildirMailInbox
from .services.ats_ack import AtsAckParser
from .services.linkedin import LinkedInAlertParser, is_own_report, message_matches_linkedin
from .services.upwork import UpworkAlertParser, message_matches_upwork


def load_mail_folder_aliases() -> dict[str, list[str]]:
    return dict(load_settings().mail_folder_aliases)


MAIL_FOLDER_ALIASES = load_mail_folder_aliases()
GMAIL_LABEL_ALIASES = MAIL_FOLDER_ALIASES


parser_registry: dict[str, AlertParser] = {
    "upwork": UpworkAlertParser(),
    "linkedin": LinkedInAlertParser(),
    "ats_ack": AtsAckParser(),
}


def inbox_factory(kind: str = "imap", **kwargs: Any) -> MailInbox:
    if kind == "imap":
        return ImapMailInbox(**kwargs)
    if kind == "maildir":
        return MaildirMailInbox(**kwargs)
    raise ValueError(f"Unsupported inbox kind: {kind}")


def message_matches_provider(provider: str, message: dict[str, Any]) -> bool:
    if is_own_report(message):
        return False
    provider_slug = slugify(provider)
    if provider_slug == "upwork":
        return message_matches_upwork(message)
    if provider_slug == "linkedin":
        return message_matches_linkedin(message)
    parser = parser_registry.get(provider_slug)
    if parser is not None:
        return parser.matches(message)
    return True


class ProviderFilterResult:
    def __init__(self, matched: list[dict[str, Any]], skipped: int) -> None:
        self.matched = matched
        self.skipped = skipped

    def to_dict(self) -> dict[str, Any]:
        return {"matched": len(self.matched), "skipped": self.skipped}


def filter_provider_messages(provider: str, messages: list[dict[str, Any]]) -> ProviderFilterResult:
    matched = [message for message in messages if message_matches_provider(provider, message)]
    return ProviderFilterResult(matched=matched, skipped=len(messages) - len(matched))


def reload_mail_folder_aliases() -> dict[str, list[str]]:
    global MAIL_FOLDER_ALIASES, GMAIL_LABEL_ALIASES
    aliases = load_mail_folder_aliases()
    MAIL_FOLDER_ALIASES = aliases
    GMAIL_LABEL_ALIASES = aliases
    return aliases

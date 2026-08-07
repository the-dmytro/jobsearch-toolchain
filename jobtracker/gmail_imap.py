"""Backward-compatible shim for jobtracker.mail."""

from .mail.generic.eml import parse_email_message
from .mail.generic.imap import GmailImapClient, MailImapClient, resolve_mail_folder
from .mail.registry import (
    GMAIL_LABEL_ALIASES,
    MAIL_FOLDER_ALIASES,
    filter_provider_messages,
    message_matches_provider,
    ProviderFilterResult,
)

__all__ = [
    "GMAIL_LABEL_ALIASES",
    "GmailImapClient",
    "MAIL_FOLDER_ALIASES",
    "MailImapClient",
    "ProviderFilterResult",
    "filter_provider_messages",
    "message_matches_provider",
    "parse_email_message",
    "resolve_mail_folder",
]

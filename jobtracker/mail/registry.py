from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_settings
from ..core.connectors import ConnectorSpec
from ..core.errors import UnknownConnectorError
from ..core.models import ConnectorBuildContext
from ..core.registry import Registry
from ..utils import slugify
from .base import AlertParser, MailInbox, MailSender
from .generic.imap import ImapMailInbox
from .generic.maildir import MaildirMailInbox
from .generic.rules_parser import RulesAlertParser
from .generic.smtp import SmtpMailSender
from .services.ats_ack import AtsAckParser
from .services.linkedin import LinkedInAlertParser, is_own_report, message_matches_linkedin
from .services.upwork import UpworkAlertParser, message_matches_upwork


def load_mail_folder_aliases() -> dict[str, list[str]]:
    return dict(load_settings().mail_folder_aliases)


MAIL_FOLDER_ALIASES = load_mail_folder_aliases()
GMAIL_LABEL_ALIASES = MAIL_FOLDER_ALIASES

parser_registry: Registry[Any] = Registry("mail.parser")
inbox_registry: Registry[Any] = Registry("mail.inbox")
sender_registry: Registry[Any] = Registry("mail.sender")


def _load_connector_entry_point(entry_point: Any) -> ConnectorSpec:
    return ConnectorSpec(slug=entry_point.name, loaded=entry_point.load())


def _register_builtin_parsers() -> None:
    parser_registry.register("upwork")(UpworkAlertParser())
    parser_registry.register("linkedin")(LinkedInAlertParser())
    parser_registry.register("ats_ack")(AtsAckParser())


_register_builtin_parsers()
parser_registry.load_entry_points("jobtracker.mail.parsers", entry_point_loader=_load_connector_entry_point)
inbox_registry.load_entry_points("jobtracker.mail.inboxes", entry_point_loader=_load_connector_entry_point)
sender_registry.load_entry_points("jobtracker.mail.senders", entry_point_loader=_load_connector_entry_point)


def build_alert_parser(
    slug: str, options: dict[str, Any] | None = None, *, root: Path | None = None
) -> AlertParser:
    config = dict(options or {})
    if str(config.get("kind") or "").lower() == "rules":
        return RulesAlertParser(config, slug=slug)
    item = parser_registry.get(slug)
    if isinstance(item, ConnectorSpec):
        return item.build(ConnectorBuildContext(root or Path.cwd(), slug, config))
    return item


def build_mail_inbox(options: dict[str, Any], *, root: Path) -> MailInbox:
    config = dict(options)
    kind = str(config.pop("kind", "imap")).lower()
    if kind == "imap":
        allowed = {key: config[key] for key in ("host", "user") if config.get(key)}
        return ImapMailInbox(**allowed)
    if kind == "maildir":
        path = Path(str(config.get("path") or ""))
        if not path.is_absolute():
            path = root / path
        return MaildirMailInbox(path)
    item = inbox_registry.get(kind)
    if isinstance(item, ConnectorSpec):
        return item.build(ConnectorBuildContext(root, kind, config))
    return item


def build_mail_sender(options: dict[str, Any], *, root: Path) -> MailSender:
    config = dict(options)
    kind = str(config.pop("kind", "smtp")).lower()
    if kind == "smtp":
        allowed = {
            key: config[key] for key in ("host", "port", "user", "sender") if config.get(key) is not None
        }
        if "from_address" in config and "sender" not in allowed:
            allowed["sender"] = config["from_address"]
        return SmtpMailSender(**allowed)
    item = sender_registry.get(kind)
    if isinstance(item, ConnectorSpec):
        return item.build(ConnectorBuildContext(root, kind, config))
    return item


def inbox_factory(kind: str = "imap", **kwargs: Any) -> MailInbox:
    return build_mail_inbox({"kind": kind, **kwargs}, root=Path.cwd())


def message_matches_provider(provider: str, message: dict[str, Any]) -> bool:
    if is_own_report(message):
        return False
    provider_slug = slugify(provider)
    if provider_slug == "upwork":
        return message_matches_upwork(message)
    if provider_slug == "linkedin":
        return message_matches_linkedin(message)
    try:
        parser = build_alert_parser(provider_slug)
    except UnknownConnectorError:
        return True
    return parser.matches(message)


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

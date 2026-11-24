"""Tests for the generic mail connectors: maildir, .eml parsing, rules, SMTP."""

from __future__ import annotations

import smtplib
import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.mail.base import OutgoingMessage, RawMessage
from jobtracker.mail.generic.eml import (
    parse_email_file,
    parse_email_message,
    raw_message_from_dict,
)
from jobtracker.mail.generic.maildir import MaildirInbox, MaildirMailInbox
from jobtracker.mail.generic.rules_parser import RulesAlertParser
from jobtracker.mail.generic.smtp import SmtpMailSender


def build_message(
    *,
    subject: str = "New jobs similar to Senior iOS Engineer",
    message_id: str = "maildir-msg-1@example.com",
    sender: str = "jobalerts-noreply@linkedin.com",
    recipient: str = "me@example.com",
    body: str = "A new iOS role matches your alert. https://www.linkedin.com/jobs/view/4242424242/",
    html: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["Message-ID"] = f"<{message_id}>"
    message["From"] = sender
    message["To"] = recipient
    message["Date"] = "Tue, 21 Apr 2026 09:00:00 +0000"
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    return message


class ParseEmailMessageTests(unittest.TestCase):
    def test_extracts_headers_body_and_links(self) -> None:
        message = build_message(
            html='<html><body><a href="https://jobs.example.com/1">Open role</a></body></html>'
        )

        parsed = parse_email_message(message.as_bytes())

        self.assertEqual(parsed["source_type"], "email")
        self.assertEqual(parsed["message_id"], "maildir-msg-1@example.com")
        self.assertEqual(parsed["external_id"], "maildir-msg-1@example.com")
        self.assertEqual(parsed["subject"], "New jobs similar to Senior iOS Engineer")
        self.assertEqual(parsed["from"], "jobalerts-noreply@linkedin.com")
        self.assertEqual(parsed["to"], "me@example.com")
        self.assertEqual(parsed["email_date"], "2026-04-21T09:00:00+00:00")
        self.assertEqual(parsed["timestamp"], parsed["email_date"])
        self.assertIn("A new iOS role matches your alert.", parsed["text"])
        self.assertEqual(parsed["raw_text"], parsed["text"])
        self.assertIn("https://jobs.example.com/1", parsed["links"])
        self.assertIn("https://www.linkedin.com/jobs/view/4242424242/", parsed["links"])

    def test_html_only_messages_fall_back_to_rendered_text(self) -> None:
        message = EmailMessage()
        message["Subject"] = "iOS role"
        message["Date"] = "Tue, 21 Apr 2026 09:00:00 +0000"
        message.set_content(
            '<html><body><p>Senior iOS Engineer</p><a href="https://jobs.example.com/2">Apply</a></body></html>',
            subtype="html",
        )

        parsed = parse_email_message(message.as_bytes())

        self.assertIn("Senior iOS Engineer", parsed["text"])
        self.assertEqual(parsed["links"], ["https://jobs.example.com/2"])

    def test_links_are_deduplicated_in_order(self) -> None:
        message = build_message(
            body="https://jobs.example.com/1 and again https://jobs.example.com/1",
            html='<a href="https://jobs.example.com/1">One</a>',
        )

        parsed = parse_email_message(message.as_bytes())

        self.assertEqual(parsed["links"], ["https://jobs.example.com/1"])

    def test_missing_headers_are_none_rather_than_raising(self) -> None:
        message = EmailMessage()
        message.set_content("body only")

        parsed = parse_email_message(message.as_bytes())

        self.assertIsNone(parsed["message_id"])
        self.assertIsNone(parsed["email_date"])
        self.assertEqual(parsed["subject"], "")

    def test_unparsable_date_header_does_not_break_parsing(self) -> None:
        message = EmailMessage()
        message["Date"] = "sometime last week"
        message.set_content("body")

        parsed = parse_email_message(message.as_bytes())

        self.assertIsNone(parsed["email_date"])
        self.assertEqual(parsed["text"], "body")

    def test_parse_email_file_reads_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alert.eml"
            path.write_bytes(build_message().as_bytes())

            parsed = parse_email_file(str(path))

            self.assertEqual(parsed["message_id"], "maildir-msg-1@example.com")

    def test_raw_message_from_dict_round_trips_known_fields(self) -> None:
        parsed = parse_email_message(build_message().as_bytes())
        parsed["maildir_path"] = "/tmp/cur/1"

        raw = raw_message_from_dict(parsed)

        self.assertIsInstance(raw, RawMessage)
        self.assertEqual(raw.sender, "jobalerts-noreply@linkedin.com")
        self.assertEqual(raw.recipient, "me@example.com")
        self.assertEqual(raw.metadata, {"maildir_path": "/tmp/cur/1"})
        self.assertEqual(raw.as_dict()["from"], "jobalerts-noreply@linkedin.com")
        self.assertEqual(raw.as_dict()["maildir_path"], "/tmp/cur/1")


class MaildirInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name) / "JobAlerts"
        for subdir in ("cur", "new", "tmp"):
            (self.root / subdir).mkdir(parents=True)

    def write_message(self, subdir: str, name: str, message: EmailMessage) -> Path:
        path = self.root / subdir / name
        path.write_bytes(message.as_bytes())
        return path

    def test_fetch_messages_reads_cur_and_new(self) -> None:
        self.write_message("cur", "1000000001.eml", build_message(message_id="cur-1@example.com"))
        self.write_message("new", "1000000002.eml", build_message(message_id="new-1@example.com"))
        inbox = MaildirMailInbox(self.root)

        messages = inbox.fetch_messages(inbox.resolve_folder("linkedin"))

        self.assertEqual(
            [message["external_id"] for message in messages],
            ["cur-1@example.com", "new-1@example.com"],
        )
        self.assertTrue(all(message["maildir_path"] for message in messages))

    def test_missing_message_id_falls_back_to_filename(self) -> None:
        message = build_message()
        del message["Message-ID"]
        self.write_message("cur", "1000000003.eml", message)

        messages = MaildirInbox(self.root).fetch_messages(self.root.name)

        self.assertEqual(messages[0]["external_id"], "1000000003.eml")

    def test_limit_keeps_the_newest_files_per_subdir(self) -> None:
        for index in range(3):
            self.write_message(
                "cur", f"100000000{index}.eml", build_message(message_id=f"cur-{index}@example.com")
            )

        messages = MaildirInbox(self.root).fetch_messages(self.root.name, limit=2)

        self.assertEqual(
            [message["external_id"] for message in messages],
            ["cur-1@example.com", "cur-2@example.com"],
        )

    def test_resolve_folder_prefers_the_explicit_folder(self) -> None:
        inbox = MaildirInbox(self.root)

        self.assertEqual(inbox.resolve_folder("linkedin"), "JobAlerts")
        self.assertEqual(inbox.resolve_folder("linkedin", "Archive"), "Archive")

    def test_list_folders_includes_the_root_and_missing_root_is_empty(self) -> None:
        self.assertIn("JobAlerts", MaildirInbox(self.root).list_folders())
        self.assertEqual(MaildirInbox(self.root.parent / "missing").list_folders(), [])

    def test_fetch_messages_on_an_unknown_folder_returns_nothing(self) -> None:
        self.assertEqual(MaildirInbox(self.root).fetch_messages("Nope"), [])


class RulesAlertParserTests(unittest.TestCase):
    RULES = {
        "sender_patterns": [r"@linkedin\.com$"],
        "subject_patterns": [r"new jobs", r"job alert"],
        "body_patterns": [r"ios"],
        "link_url_patterns": [r"https?://www\.linkedin\.com/jobs/view/"],
        "exclude_subject_patterns": [r"verification code"],
    }

    def message(self, **overrides) -> dict:
        base = {
            "source_type": "email",
            "external_id": "linkedin-1",
            "from": "jobalerts-noreply@linkedin.com",
            "subject": "New jobs similar to Senior iOS Engineer",
            "text": "See the iOS roles matching your alert.",
            "timestamp": "2026-04-21T09:00:00+00:00",
            "links": [
                "https://www.linkedin.com/jobs/view/4242424242/",
                "https://www.linkedin.com/feed/",
            ],
        }
        base.update(overrides)
        return base

    def test_matches_when_every_configured_group_matches(self) -> None:
        self.assertTrue(RulesAlertParser(self.RULES).matches(self.message()))

    def test_parse_returns_the_matched_links_only(self) -> None:
        parsed = RulesAlertParser(self.RULES).parse(self.message())

        self.assertEqual(parsed["parser"], "rules_alert_parser")
        self.assertEqual(parsed["external_id"], "linkedin-1")
        self.assertEqual(parsed["timestamp"], "2026-04-21T09:00:00+00:00")
        self.assertEqual(parsed["matched_links"], ["https://www.linkedin.com/jobs/view/4242424242/"])

    def test_non_matching_sender_is_rejected(self) -> None:
        parser = RulesAlertParser(self.RULES)
        message = self.message(**{"from": "noreply@example.com"})

        self.assertFalse(parser.matches(message))
        self.assertIsNone(parser.parse(message))

    def test_exclude_patterns_veto_an_otherwise_matching_message(self) -> None:
        parser = RulesAlertParser(self.RULES)

        self.assertFalse(parser.matches(self.message(subject="Your LinkedIn verification code")))

    def test_exclude_sender_and_body_patterns(self) -> None:
        parser = RulesAlertParser({"exclude_sender_patterns": [r"@spam\.example$"]})
        self.assertFalse(parser.matches(self.message(**{"from": "bulk@spam.example"})))

        body_parser = RulesAlertParser({"exclude_body_patterns": [r"unsubscribe"]})
        self.assertFalse(body_parser.matches(self.message(text="Please unsubscribe here.")))

    def test_empty_rules_match_everything(self) -> None:
        parser = RulesAlertParser({})

        self.assertTrue(parser.matches({"subject": "anything"}))
        self.assertEqual(parser.parse({"subject": "anything"})["matched_links"], [])

    def test_link_patterns_require_at_least_one_matching_link(self) -> None:
        parser = RulesAlertParser({"link_url_patterns": [r"linkedin\.com/jobs/view/"]})

        self.assertFalse(parser.matches(self.message(links=["https://www.linkedin.com/feed/"])))
        self.assertFalse(parser.matches(self.message(links=[])))


class SmtpMailSenderTests(unittest.TestCase):
    def build_sender(self) -> SmtpMailSender:
        return SmtpMailSender(
            host="smtp.example.com",
            port=465,
            user="robot@example.com",
            password="app-password",
            sender="robot@example.com",
        )

    def test_missing_credentials_raise_at_construction(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch("jobtracker.mail.generic.smtp.load_env_file"):
                with self.assertRaises(RuntimeError):
                    SmtpMailSender()

    def test_settings_are_read_from_the_environment(self) -> None:
        env = {
            "JOBTRACKER_SMTP_HOST": "smtp.example.com",
            "JOBTRACKER_SMTP_PORT": "2465",
            "JOBTRACKER_SMTP_USER": "robot@example.com",
            "JOBTRACKER_SMTP_PASSWORD": "app-password",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch("jobtracker.mail.generic.smtp.load_env_file"):
                sender = SmtpMailSender()

        self.assertEqual(sender.host, "smtp.example.com")
        self.assertEqual(sender.port, 2465)
        self.assertEqual(sender.default_sender, "robot@example.com")

    def test_send_logs_in_and_delivers_the_message(self) -> None:
        sender = self.build_sender()
        message = OutgoingMessage(
            sender="robot@example.com",
            recipient="me@example.com",
            subject="iOS triage report",
            body="Two roles worth a look.",
        )

        with mock.patch.object(smtplib, "SMTP_SSL") as smtp_ssl:
            receipt = sender.send(message)

        smtp_ssl.assert_called_once()
        self.assertEqual(smtp_ssl.call_args.args[0], "smtp.example.com")
        self.assertEqual(smtp_ssl.call_args.args[1], 465)
        connection = smtp_ssl.return_value.__enter__.return_value
        connection.login.assert_called_once_with("robot@example.com", "app-password")
        connection.send_message.assert_called_once()
        delivered = connection.send_message.call_args.args[0]
        self.assertEqual(delivered["To"], "me@example.com")
        self.assertEqual(delivered["From"], "robot@example.com")
        self.assertEqual(delivered["Subject"], "iOS triage report")
        self.assertIn("Two roles worth a look.", delivered.get_content())
        self.assertTrue(receipt.sent)
        self.assertEqual(receipt.recipient, "me@example.com")
        self.assertEqual(receipt.subject, "iOS triage report")

    def test_send_falls_back_to_the_default_sender(self) -> None:
        sender = self.build_sender()
        message = OutgoingMessage(sender="", recipient="me@example.com", subject="Report", body="body")

        with mock.patch.object(smtplib, "SMTP_SSL") as smtp_ssl:
            sender.send(message)

        delivered = smtp_ssl.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(delivered["From"], "robot@example.com")

    def test_send_requires_a_recipient(self) -> None:
        sender = self.build_sender()
        message = OutgoingMessage(sender="robot@example.com", recipient="  ", subject="Report", body="body")

        with mock.patch.object(smtplib, "SMTP_SSL") as smtp_ssl:
            with self.assertRaises(ValueError):
                sender.send(message)

        smtp_ssl.assert_not_called()


if __name__ == "__main__":
    unittest.main()

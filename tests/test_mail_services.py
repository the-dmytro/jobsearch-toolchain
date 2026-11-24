"""Tests for the provider-specific alert/acknowledgement mail parsers."""

from __future__ import annotations

import unittest
from unittest import mock

from hermetic import set_up_module as setUpModule  # noqa: F401
from hermetic import tear_down_module as tearDownModule  # noqa: F401

from jobtracker.mail.registry import filter_provider_messages, message_matches_provider, parser_registry
from jobtracker.mail.services.ats_ack import AtsAckParser
from jobtracker.mail.services.linkedin import (
    LinkedInAlertParser,
    is_own_report,
    message_matches_linkedin,
)
from jobtracker.mail.services.upwork import (
    UpworkAlertParser,
    message_matches_upwork,
    parse_upwork_source_item,
)

NO_OWN_SENDERS = {"JOBTRACKER_OWN_SENDERS": ""}

UPWORK_ALERT_TEXT = (
    "New job alert Hi there, this job matches your saved search. "
    "---------- SwiftUI checkout fix: "
    "https://www.upwork.com/jobs/~022056285060802688779?link=title&n=null "
    "Hourly: $15.00 - $30.00 · Est. time: 1 to 3 months · Posted Mon, May 18 "
    "We need help with a native iOS checkout issue. "
    "more: https://www.upwork.com/jobs/~022056285060802688779?link=more&n=null "
    "Skills: iOS: https://www.upwork.com/s/emails/nx/search/jobs/?x=1 "
    "Payment verified · 5.0 stars · $4K spent · HKG"
)


class AtsAckParserTests(unittest.TestCase):
    def greenhouse_message(self, **overrides) -> dict:
        base = {
            "source_type": "email",
            "external_id": "gh-ack-1",
            "message_id": "gh-ack-1",
            "from": "no-reply@greenhouse.io",
            "subject": "Application received",
            "text": "Thank you for applying to Acme Corp. Application ID: AB12CD34.",
            "timestamp": "2026-04-21T09:00:00+00:00",
            "links": ["https://boards.greenhouse.io/acme/jobs/991"],
        }
        base.update(overrides)
        return base

    def test_matches_a_greenhouse_acknowledgement(self) -> None:
        self.assertTrue(AtsAckParser().matches(self.greenhouse_message()))

    def test_parse_identifies_provider_and_application_id(self) -> None:
        parsed = AtsAckParser().parse(self.greenhouse_message())

        self.assertEqual(parsed["parser"], "ats_ack_parser")
        self.assertEqual(parsed["ats_provider"], "greenhouse")
        self.assertEqual(parsed["application_id"], "AB12CD34")
        self.assertEqual(parsed["external_id"], "gh-ack-1")
        self.assertEqual(parsed["subject"], "Application received")
        self.assertEqual(parsed["timestamp"], "2026-04-21T09:00:00+00:00")

    def test_application_id_falls_back_to_the_link_path(self) -> None:
        parsed = AtsAckParser().parse(
            self.greenhouse_message(
                text="Thanks for applying to Acme Corp.",
                links=["https://boards.greenhouse.io/acme/applications/778899"],
            )
        )

        self.assertEqual(parsed["application_id"], "778899")

    def test_lever_acknowledgements_are_recognised(self) -> None:
        parsed = AtsAckParser().parse(
            {
                "external_id": "lever-ack-1",
                "from": "no-reply@jobs.lever.co",
                "subject": "Thanks for applying",
                "text": "Your application was received.",
                "links": ["https://jobs.lever.co/acme/1234"],
            }
        )

        self.assertEqual(parsed["ats_provider"], "lever")

    def test_unrelated_mail_does_not_match(self) -> None:
        parser = AtsAckParser()
        message = {
            "from": "newsletter@example.com",
            "subject": "Weekly digest",
            "text": "Nothing to see here.",
            "links": [],
        }

        self.assertFalse(parser.matches(message))
        self.assertIsNone(parser.parse(message))

    def test_custom_rules_replace_the_defaults(self) -> None:
        parser = AtsAckParser({"acme_ats": {"sender_patterns": [r"@acme-ats\.example$"]}})

        parsed = parser.parse({"from": "bot@acme-ats.example", "subject": "Received", "links": []})

        self.assertEqual(parsed["ats_provider"], "acme_ats")
        self.assertIsNone(parsed["application_id"])


class LinkedInAlertParserTests(unittest.TestCase):
    def alert(self, **overrides) -> dict:
        base = {
            "source_type": "email",
            "external_id": "linkedin-alert-1",
            "from": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            "subject": "New jobs similar to Senior iOS Engineer",
            "text": "See jobs matching your alert on LinkedIn.",
            "timestamp": "2026-04-21T09:00:00+00:00",
            "links": [
                "https://www.linkedin.com/jobs/view/4242424242/",
                "https://www.linkedin.com/feed/",
            ],
        }
        base.update(overrides)
        return base

    def test_parse_extracts_job_view_links(self) -> None:
        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            parsed = LinkedInAlertParser().parse(self.alert())

        self.assertEqual(parsed["parser"], "linkedin_alert_parser")
        self.assertEqual(parsed["external_id"], "linkedin-alert-1")
        self.assertEqual(parsed["subject"], "New jobs similar to Senior iOS Engineer")
        self.assertEqual(parsed["timestamp"], "2026-04-21T09:00:00+00:00")
        self.assertEqual(parsed["job_links"], ["https://www.linkedin.com/jobs/view/4242424242/"])

    def test_unknown_sender_addresses_are_ignored(self) -> None:
        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            message = self.alert(**{"from": "LinkedIn <messages-noreply@linkedin.com>"})

            self.assertFalse(message_matches_linkedin(message))
            self.assertIsNone(LinkedInAlertParser().parse(message))

    def test_application_and_security_mail_is_excluded(self) -> None:
        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            self.assertFalse(
                message_matches_linkedin(
                    self.alert(
                        subject="Your application was sent to Acme",
                        text="View your application for this LinkedIn job.",
                    )
                )
            )
            self.assertFalse(
                message_matches_linkedin(
                    self.alert(subject="Your LinkedIn verification code", text="Use this code to sign in.")
                )
            )

    def test_own_report_mail_is_never_treated_as_an_alert(self) -> None:
        report = {
            "from": "Automation <robot@example.com>",
            "subject": "LinkedIn job triage — 2026-04-21",
            "text": "Automation summary",
            "links": [],
        }

        with mock.patch.dict("os.environ", {"JOBTRACKER_OWN_SENDERS": "robot@example.com"}, clear=False):
            self.assertTrue(is_own_report(report))
            self.assertFalse(message_matches_linkedin(report))

    def test_subject_based_own_report_detection(self) -> None:
        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            self.assertTrue(
                is_own_report({"from": "me@example.com", "subject": "Upwork job alerts - 2026-04-21"})
            )


class UpworkAlertParserTests(unittest.TestCase):
    def alert(self, **overrides) -> dict:
        base = {
            "source_type": "email",
            "external_id": "upwork-email-1",
            "message_id": "upwork-email-1",
            "from": "Upwork <noreply@upwork.com>",
            "subject": "New job alert: SwiftUI checkout fix",
            "timestamp": "2026-05-18T08:11:27+00:00",
            "text": UPWORK_ALERT_TEXT,
            "links": ["https://www.upwork.com/jobs/~022056285060802688779/"],
        }
        base.update(overrides)
        return base

    def test_matches_upwork_alert_mail(self) -> None:
        self.assertTrue(UpworkAlertParser().matches(self.alert()))
        self.assertTrue(message_matches_upwork(self.alert()))

    def test_parse_returns_deterministic_job_cards(self) -> None:
        parsed = UpworkAlertParser().parse(self.alert())

        self.assertEqual(parsed["parser"], "upwork_alert_parser")
        self.assertEqual(len(parsed["cards"]), 1)
        card = parsed["cards"][0]
        self.assertEqual(card["external_id"], "022056285060802688779")
        self.assertEqual(card["title"], "SwiftUI checkout fix")
        self.assertEqual(card["canonical_url"], "https://www.upwork.com/jobs/~022056285060802688779/")
        self.assertEqual(card["engagement_type"], "hourly")
        self.assertEqual(card["budget_type"], "hourly")
        self.assertEqual(card["compensation_text"], "Hourly: $15.00 - $30.00")
        self.assertEqual(card["estimated_time"], "1 to 3 months")
        self.assertEqual(card["posted_text"], "Mon, May 18")
        self.assertEqual(card["skills"], ["iOS"])
        self.assertEqual(card["client_economics"], "Payment verified · 5.0 stars · $4K spent · HKG")
        self.assertEqual(card["parser_confidence"], "high")
        self.assertEqual(card["parser_missing_fields"], [])

    def test_non_upwork_mail_does_not_match(self) -> None:
        parser = UpworkAlertParser()
        message = {"from": "newsletter@example.com", "subject": "Weekly digest", "text": "Nothing here."}

        self.assertFalse(parser.matches(message))
        self.assertIsNone(parser.parse(message))

    def test_upwork_mail_without_job_cards_parses_to_none(self) -> None:
        message = self.alert(text="An Upwork job digest with no parseable cards.")

        self.assertTrue(UpworkAlertParser().matches(message))
        self.assertIsNone(UpworkAlertParser().parse(message))

    def test_parse_source_item_ignores_the_view_job_details_footer(self) -> None:
        text = (
            UPWORK_ALERT_TEXT
            + " ---------- View job details: https://www.upwork.com/jobs/~022056285060802688779?frkscc=abc"
        )

        cards = parse_upwork_source_item({"text": text, "subject": "New job alert: SwiftUI checkout fix"})

        self.assertEqual(len(cards), 1)

    def test_empty_source_item_yields_no_cards(self) -> None:
        self.assertEqual(parse_upwork_source_item({}), [])


class MailRegistryTests(unittest.TestCase):
    def test_registry_exposes_the_builtin_parsers(self) -> None:
        self.assertLessEqual({"upwork", "linkedin", "ats_ack"}, set(parser_registry.all()))

    def test_message_matches_provider_routes_to_the_right_parser(self) -> None:
        upwork = {
            "from": "Upwork <noreply@upwork.com>",
            "subject": "New job: SwiftUI prototype",
            "text": "A new job matches your saved search.",
            "links": [],
        }
        linkedin = {
            "from": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
            "subject": "New jobs similar to Senior iOS Engineer",
            "text": "See jobs matching your alert on LinkedIn.",
            "links": [],
        }

        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            self.assertTrue(message_matches_provider("upwork", upwork))
            self.assertFalse(message_matches_provider("upwork", linkedin))
            self.assertTrue(message_matches_provider("linkedin", linkedin))
            self.assertFalse(message_matches_provider("linkedin", upwork))

    def test_filter_provider_messages_counts_skips(self) -> None:
        messages = [
            {
                "external_id": "upwork-1",
                "from": "Upwork <noreply@upwork.com>",
                "subject": "New job: SwiftUI prototype",
                "text": "A new job matches your saved search.",
                "links": [],
            },
            {
                "external_id": "other-1",
                "from": "newsletter@example.com",
                "subject": "Weekly digest",
                "text": "Nothing here.",
                "links": [],
            },
        ]

        with mock.patch.dict("os.environ", NO_OWN_SENDERS, clear=False):
            result = filter_provider_messages("upwork", messages)

        self.assertEqual([item["external_id"] for item in result.matched], ["upwork-1"])
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.to_dict(), {"matched": 1, "skipped": 1})


if __name__ == "__main__":
    unittest.main()

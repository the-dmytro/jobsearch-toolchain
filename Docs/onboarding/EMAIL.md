# Email

Email is optional. Choose IMAP or maildir for inbox access, a built-in/rules/plugin parser, and SMTP or a sender plugin for outbound mail.

Keep passwords in `.env`. Store non-secret host, port, user name, folder aliases, and parser rules in ignored TOML. Grant the narrowest mailbox access available and document revocation.

```bash
.venv/bin/python -m jobtracker discover-mail-folders
.venv/bin/python -m jobtracker fetch-mail-folder --provider <provider> --limit 20
```

An EML file is a parser input for tests/imports, not an inbox connector. For offline inbox tests, use a maildir. See [mail connector guide](../connectors/writing-a-mail-connector.md).

Interview invites and scheduling e-mails can feed an optional calendar: `calendar parse --imap FOLDER:UID` reads one message read-only and classifies it. See [Calendar](CALENDAR.md).

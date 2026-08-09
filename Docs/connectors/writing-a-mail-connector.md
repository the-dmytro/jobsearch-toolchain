# Writing a mail connector

Mail has three independent products: inbox, parser, and sender.

## Built-ins

```toml
[mail.inbox]
kind = "imap"
host = "imap.example.com"
user = "person@example.com"

[mail.outbox]
kind = "smtp"
host = "smtp.example.com"
port = 465
user = "person@example.com"
from_address = "reports@example.com"
```

Passwords come from `.env`. Use `kind = "maildir"` plus a root-relative `path` for an offline inbox. EML parsing is an import/test helper, not an inbox kind.

## Rules parser

```toml
[mail.parsers.example]
kind = "rules"
senders = ["alerts@provider.example"]
subject_patterns = ["new role", "job alert"]
link_patterns = ["https://jobs\\.example/jobs/\\d+"]
provider_slug = "example"
```

Rules parsers and code parsers implement the same dictionary API:

```python
matches(message: dict[str, object]) -> bool
parse(message: dict[str, object]) -> dict[str, object] | None
```

`RawMessage` fields are `message_id`, `external_id`, `subject`, `sender`, `recipient`, `email_date`, `timestamp`, `text`, `raw_text`, `links`, and `metadata`.

## Plugin factories

Entry-point groups are `jobtracker.mail.parsers`, `jobtracker.mail.inboxes`, and `jobtracker.mail.senders`. Each value is preferably a factory accepting `ConnectorBuildContext`; zero-argument classes/instances are deprecated compatibility forms.

```toml
[project.entry-points."jobtracker.mail.parsers"]
example = "private_mail.plugin:build_parser"
```

Add fixture messages and test sender matching, parsing, stable source IDs, folder behavior, and that health/errors never expose credentials.

# Writing a mail connector

Mail connectors cover **inbox fetch**, **outbound send**, and **alert parsing**.

## Inbox (general-purpose IMAP)

**`config/jobsearch.toml`:**

```toml
[mail.inbox]
kind = "imap"
host = "imap.mail.example.com"
user = "jobs@example.com"
folder_aliases.upwork = ["Upwork", "job/Upwork"]
folder_aliases.linkedin = ["job/LinkedIn", "Jobs/Alerts/LinkedIn"]
```

Password via `.env`: `JOBTRACKER_IMAP_PASSWORD=...`

**CLI:**

```bash
python -m jobtracker discover-mail-folders
python -m jobtracker fetch-mail-folder --provider upwork --limit 20 \
  --output outputs/automation-payloads/upwork-mail-source.payload.json
```

## Rules-based parser (config only)

For job alert emails without custom code:

```toml
[mail.parsers.my_alerts]
kind = "rules"
senders = ["alerts@example.com", "noreply@jobs.example.com"]
subject_patterns = ["new job", "job alert"]
link_patterns = ["https://jobs.example.com/view/\\d+"]
provider_slug = "example"
```

## Service-specific parser (in-tree)

**`jobtracker/mail/services/myprovider.py`:**

```python
from __future__ import annotations

import re
from typing import ClassVar

from jobtracker.core.models import Candidate
from jobtracker.mail.base import AlertParser, RawMessage
from jobtracker.mail.registry import register_parser


@register_parser
class MyProviderParser(AlertParser):
    slug: ClassVar[str] = "myprovider"

    def matches(self, message: RawMessage) -> bool:
        return "alerts@myprovider.com" in (message.from_address or "")

    def parse(self, message: RawMessage) -> list[Candidate]:
        candidates = []
        for url in re.findall(r"https://myprovider.com/jobs/(\d+)", message.body_text or ""):
            candidates.append(Candidate(
                external_id=url,
                title=message.subject or "Unknown",
                source_url=f"https://myprovider.com/jobs/{url}",
                apply_url=f"https://myprovider.com/jobs/{url}",
            ))
        return candidates
```

## Outbound (SMTP)

```toml
[mail.outbox]
kind = "smtp"
host = "smtp.example.com"
port = 465
from_address = "reports@example.com"
```

```bash
python -m jobtracker send-report-email \
  --provider upwork \
  --run-key upwork-2026-01-01 \
  --subject "Upwork report" \
  --body-file report.md \
  --to jobs@example.com
```

Missing `--to` / `JOBTRACKER_REPORT_EMAIL_TO` is an error (no hardcoded default).

## Local / offline testing

```toml
[mail.inbox]
kind = "eml"
path = "tests/fixtures/mail/sample-alert.eml"
```

Or maildir:

```toml
[mail.inbox]
kind = "maildir"
path = "/path/to/Maildir"
```

## Out-of-tree plugin

```toml
[project.entry-points."jobtracker.mail.parsers"]
myprovider = "my_mail_plugin.parser:MyProviderParser"
```

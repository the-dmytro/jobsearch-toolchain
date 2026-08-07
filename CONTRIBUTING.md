# Contributing

## Architecture

- **Connectors** live in `jobtracker/sources/`, `jobtracker/mail/`, `jobtracker/store/`, `jobtracker/notify/`
- **General-purpose** connectors are config-driven (TOML `kind = "rss"` etc.)
- **Service-specific** connectors are thin Python classes in `services/` subdirectories
- **Payload contract** is defined in `Docs/DB/AUTOMATION_PAYLOAD_CONTRACT.md` — do not change without discussion

## Adding a job source

See [docs/connectors/writing-a-source.md](docs/connectors/writing-a-source.md).

## Adding a mail parser

See [docs/connectors/writing-a-mail-connector.md](docs/connectors/writing-a-mail-connector.md).

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
python3 -m unittest discover -s tests
python3 scripts/scan_pii.py
```

## Pull requests

- One logical change per PR
- All tests must pass
- PII scan must pass (`python3 scripts/scan_pii.py`)
- No personal data in tracked files

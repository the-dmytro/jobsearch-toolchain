# Troubleshooting

Start with:

```bash
.venv/bin/python --version
.venv/bin/python -m jobtracker doctor --skip-network
.venv/bin/python -m unittest discover -s tests
```

- `error` from doctor means config could not be loaded or validated; fix that first.
- `action_required` means the config loaded but a selected component or profile input needs work.
- Relative paths unexpectedly point elsewhere: pass `--root` and inspect the configured path; v1 resolves from that root.
- SQLite replay appears duplicated: confirm producers reuse the same `run.run_key`.
- PostgreSQL is unavailable: keep local payload artifacts and replay later.
- Connector is unknown: inspect `doctor`, the configured slug, installed entry-point group, and factory contract.

Report exact errors without credentials. Never paste `.env` contents into an issue.

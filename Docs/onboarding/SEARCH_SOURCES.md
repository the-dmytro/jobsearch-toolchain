# Search sources

Select only services the user wants. Add a source slug to a pipeline's `providers` list.

- Config-only: use `rss`, `jsonld`, `html`, `json_api`, `sitemap`, or `csv` under `[sources.<slug>]`.
- In-tree service: implement `JobSource` and register it.
- Private plugin: install from a local path or Git URL and expose `jobtracker.sources`.

Test a single source before a pipeline:

```bash
.venv/bin/python -m jobtracker fetch-source <source-slug> --dry-run
```

Provider-specific commands remain aliases during v0.2. Prefer `fetch-source` in new instructions. See [writing a source](../connectors/writing-a-source.md).

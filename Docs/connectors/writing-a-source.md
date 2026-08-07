# Writing a job source connector

Three ways to add a job source, from easiest to most involved.

## 1. Config only (no Python)

For boards with RSS, JSON-LD, or a JSON API.

**`config/jobsearch.toml`:**

```toml
[sources.acme_careers]
kind = "jsonld"
listing_url = "https://acme.example.com/careers"
detail_limit = 10

[sources.acme_careers.role_lane]
include_terms = ["engineer", "developer"]
exclude_terms = ["intern", "manager"]
```

**Run:**

```bash
python -m jobtracker run jobboards --dry-run
# or add acme_careers to a pipeline's sources list
```

Supported `kind` values: `rss`, `jsonld`, `html`, `json-api`, `sitemap`, `csv`.

### HTML selector example

```toml
[sources.custom_board]
kind = "html"
listing_url = "https://jobs.example.com/list"
list_selector = "article.job-card a.title"
detail_selector = "div.job-description"
link_attr = "href"
```

## 2. In-tree service connector

For named providers with custom parsing logic.

**`jobtracker/sources/services/myboard.py`:**

```python
from __future__ import annotations

from typing import Iterable

from jobtracker.core.context import SourceContext
from jobtracker.core.models import Candidate
from jobtracker.sources.base import JobSource
from jobtracker.sources.registry import register_source
from jobtracker.sources.shared.infer import matches_lane
from jobtracker.sources.shared.fetch import LiveFetcher


@register_source
class MyBoardSource(JobSource):
    slug = "myboard"

    def discover(self, ctx: SourceContext) -> Iterable[Candidate]:
        url = ctx.options["listing_url"]
        html = ctx.fetcher.get_text(url, "list")
        # ... parse html into Candidate objects ...
        yield Candidate(
            external_id="123",
            title="Example Role",
            source_url="https://myboard.example.com/jobs/123",
            apply_url="https://myboard.example.com/jobs/123/apply",
        )

    def health(self, ctx: SourceContext):
        from jobtracker.core.context import HealthReport
        return HealthReport(ok=True, message="myboard reachable")
```

**Enable in TOML:**

```toml
[sources.myboard]
listing_url = "https://myboard.example.com/jobs"
```

**Test with fixtures:**

```bash
python -m jobtracker fetch-myboard --dry-run --fixture-dir tests/fixtures/myboard
```

## 3. Out-of-tree plugin

Publish a package without forking.

**`my_jobboard_plugin/pyproject.toml`:**

```toml
[project]
name = "my-jobboard-plugin"
version = "0.1.0"
dependencies = ["jobsearch-tracker"]

[project.entry-points."jobtracker.sources"]
myboard = "my_jobboard_plugin.source:MyBoardSource"
```

**`my_jobboard_plugin/source.py`:** same class as above, without `@register_source` (entry point registers it).

**Install:**

```bash
pip install ./my_jobboard-plugin
python -m jobtracker doctor   # should list myboard in available sources
```

## Contract

Every source yields `Candidate` objects. The registry builds automation payloads via `sources/shared/payload.py`. Do not change the payload JSON shape — see `Docs/DB/AUTOMATION_PAYLOAD_CONTRACT.md`.

## Testing

Add fixture HTML/JSON under `jobtracker/fixtures/provider_fetch/` and a test in `tests/test_provider_fetch.py` or `tests/test_connector_contract.py`.

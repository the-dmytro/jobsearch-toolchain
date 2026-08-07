from __future__ import annotations

from jobtracker.sources.generic.json_api import JsonApiSource
from jobtracker.sources.registry import register_source


@register_source
class AshbySource(JsonApiSource):
    slug = "ashby"
    api_url_template = "https://api.ashbyhq.com/posting-api/job-board/{token}"
    jobs_key = "jobs"
    external_id_prefix = "ashby:"

    def health(self, ctx):
        return []

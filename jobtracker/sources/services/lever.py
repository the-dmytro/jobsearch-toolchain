from __future__ import annotations

from jobtracker.sources.generic.json_api import JsonApiSource
from jobtracker.sources.registry import register_source


@register_source
class LeverSource(JsonApiSource):
    slug = "lever"
    api_url_template = "https://api.lever.co/v0/postings/{token}?mode=json"
    jobs_key = None
    external_id_prefix = "lever:"

    def health(self, ctx):
        return []

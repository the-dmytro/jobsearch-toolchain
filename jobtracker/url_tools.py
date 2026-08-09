from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .utils import normalize_space

TRACKING_PARAMS = {
    "alternatechannel",
    "eid",
    "ebp",
    "gh_src",
    "lever-source",
    "midtoken",
    "midsig",
    "refid",
    "source",
    "trackingid",
    "trk",
    "trkemail",
}


def clean_url(value: str | None) -> str | None:
    url = normalize_space(value)
    if not url.startswith(("http://", "https://")):
        return None

    parts = urlsplit(url)
    host = parts.netloc.lower()
    path = parts.path

    if host.endswith("linkedin.com"):
        linkedin_match = re.search(r"(\d{7,})", path)
        if linkedin_match:
            job_id = linkedin_match.group(1)
            return urlunsplit((parts.scheme, "www.linkedin.com", f"/jobs/view/{job_id}/", "", ""))

    kept_params = []
    for key, param_value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            continue
        kept_params.append((key, param_value))

    query = urlencode(kept_params, doseq=True)
    return urlunsplit((parts.scheme, host, path, query, ""))

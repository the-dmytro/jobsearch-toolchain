# Writing a calendar connector

A calendar connector stores iCalendar objects in named calendars. The host owns everything else: iTIP classification, time-zone resolution, the managed-event marker, stale-update checks, rendering, and read-back verification. A backend only moves `.ics` text.

## Built-ins

```toml
[calendar]
kind = "caldav"
url = "https://caldav.example.com/"
calendar = "Interviews"
user_env = "JOBTRACKER_CALDAV_USER"
password_env = "JOBTRACKER_CALDAV_PASSWORD"
```

Use `kind = "icsdir"` with a root-relative `path` for an offline calendar. Credentials are read from the environment variables named by `user_env` and `password_env`. The config loader rejects literal `user`, `password`, or `token` keys in `[calendar]`.

## Protocol

```python
slug: str
calendars() -> list[CalendarInfo]                       # (name, url)
object_url(calendar_url: str, uid: str) -> str
get(url: str) -> CalendarObject | None                  # (url, etag, data)
by_range(calendar_url: str, start: datetime, end: datetime) -> list[CalendarObject]
all_events(calendar_url: str) -> list[CalendarObject]
put(url: str, ics: str, etag: str | None) -> int        # etag None = create only
delete(url: str, etag: str | None) -> None
health() -> list[str]
```

`CalendarInfo` and `CalendarObject` are named tuples in `jobtracker.calendar.base`. Optional methods:

- `calendar_url(name) -> str` resolves a calendar without listing them (the `icsdir` backend creates the folder).
- `by_uid(calendar_url, uid, around) -> list[CalendarObject]` replaces the host's lookup. Without it the host tries `get(object_url(...))`, then `by_range` within three days of the expected start, then `all_events`. This order exists because some CalDAV servers reject a UID `prop-filter` with HTTP 412.

`put` must honour `etag` as an `If-Match` precondition and `None` as `If-None-Match: *`, and raise on failure. `health()` must not send writes or expose secrets.

## Plugin factory

```toml
[project.entry-points."jobtracker.calendars"]
private_calendar = "private_calendar.plugin:build_backend"
```

```python
def build_backend(context):
    # context.options is the [calendar] table; read secrets from os.environ
    return PrivateCalendarBackend(context.options)
```

Built-in kinds (`caldav`, `icsdir`) take precedence over a plugin with the same slug.

## Tests

Use synthetic invites and reserved domains. Cover create-only `put`, `If-Match` conflicts, `by_range` boundaries, lookup when the object URL differs from the UID, delete, and `health()` without credentials. The host-side behaviour is covered in `tests/test_calendar.py`; a backend can reuse its `FakeBackend` shape.

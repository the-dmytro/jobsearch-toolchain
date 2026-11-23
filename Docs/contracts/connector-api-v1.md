# Connector API v1

Status: frozen for JobSearch Toolchain v0.2.x

Owner and freeze authority: `jobsearch-toolchain` maintainers
Compatibility boundary: installed connector packages and the host CLI

## Factory boundary

Every entry point resolves to one of these forms:

1. Preferred: a callable accepting `ConnectorBuildContext` and returning the required protocol implementation.
2. Transitional: a zero-argument class or an already-created protocol implementation. The host adapts it and emits a deprecation warning.

`ConnectorBuildContext` contains only:

- `root: pathlib.Path`, the selected project root;
- `slug: str`, normalized from the configured or entry-point name;
- `options: Mapping[str, Any]`, the resolved non-secret connector configuration.

Secrets are read from documented environment variables by the connector. They must not be placed in TOML or returned by health checks.

## Entry-point groups

| Group | Product | Required protocol |
| --- | --- | --- |
| `jobtracker.sources` | Job discovery source | `JobSource` |
| `jobtracker.mail.parsers` | Alert parser | `AlertParser` |
| `jobtracker.mail.inboxes` | Mail inbox | `MailInbox` |
| `jobtracker.mail.senders` | Outbound mail sender | `MailSender` |
| `jobtracker.stores` | Job data store | `JobStore` |
| `jobtracker.notifiers` | Run notifier | `Notifier` |
| `jobtracker.calendars` | Calendar backend | `CalendarBackend` (amendment 1) |
| `jobtracker.db_connectors` | How the PostgreSQL store reaches its database | `DatabaseConnector`, DB-CONNECTOR-V1 (amendment 2, [guide](../connectors/writing-a-database-connector.md)) |

Built-ins take precedence over a plugin with the same normalized slug. Unknown slugs fail with an error that lists available connectors. A plugin load failure is reported by `doctor`; it must not expose secrets.

## Protocols

### JobSource

```python
slug: str
discover(ctx: CollectionContext) -> tuple[list[Candidate], str, list[str]]
health(ctx: CollectionContext) -> list[str]
```

The status is `completed`, `partial`, or `failed`; blockers are durable human-readable reasons. The host owns payload construction and validation.

### AlertParser

```python
matches(message: dict[str, Any]) -> bool
parse(message: dict[str, Any]) -> dict[str, Any] | None
```

### MailInbox and MailSender

```python
list_folders() -> list[str]
resolve_folder(provider: str, explicit_folder: str | None = None) -> str
fetch_messages(folder: str, since: str | None = None, limit: int | None = None) -> list[dict[str, Any]]

send(message: OutgoingMessage) -> SendReceipt
```

### JobStore

```python
upsert_run_payload(provider_slug: str, payload_path: str, report_path: str | None = None) -> UpsertResult
check_duplicates(provider_slug: str, company: str | None, title: str | None, external_id: str | None = None) -> list[DuplicateMatch]
export_application_summary(application_id: str) -> str
verify_run(run_key: str) -> dict | None   # recommended; readback, None when the run is not stored
```

Writes are idempotent by `run.run_key` and are read back with `verify_run`. With the SQLite store, retained JSON payloads are the audit, replay and recovery boundary. With the shared PostgreSQL store, the database is the record: local payloads are temporary and `prune-local` removes them once the database holds their content. Stores without `verify_run` report `verified: false`.

### Notifier

```python
slug: str
notify(report: RunReport) -> dict[str, Any]
health() -> list[str]
```

### CalendarBackend (amendment 1)

```python
slug: str
calendars() -> list[CalendarInfo]
object_url(calendar_url: str, uid: str) -> str
get(url: str) -> CalendarObject | None
by_range(calendar_url: str, start: datetime, end: datetime) -> list[CalendarObject]
all_events(calendar_url: str) -> list[CalendarObject]
put(url: str, ics: str, etag: str | None) -> int
delete(url: str, etag: str | None) -> None
health() -> list[str]
```

Optional: `calendar_url(name) -> str` and `by_uid(calendar_url, uid, around) -> list[CalendarObject]`. `put` treats `etag` as `If-Match` and `None` as create-only. The host owns iTIP classification, time zones, the `X-JOBSEARCH-KEY` managed marker, stale-update checks, and read-back verification; written events never carry `ORGANIZER` or `ATTENDEE`. See the [calendar connector guide](../connectors/writing-a-calendar-connector.md).

## Amendments

1. v0.2 (backward compatible): adds the optional `jobtracker.calendars` group and the `CalendarBackend` protocol. Existing groups and signatures are unchanged.

## Change control

A breaking signature, entry-point group, payload requirement, configuration rule, or error-semantic change requires a new contract version. Dependent examples, fixture plugins, onboarding instructions, and integration tests must be updated against that same version before release.

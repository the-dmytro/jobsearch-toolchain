# Calendar

The calendar connector is optional. It keeps interview and recruiter-call events in one calendar in step with the invites and confirmation e-mails you receive. It reads `.ics` invites (Google Calendar, Microsoft Exchange/Outlook, ATS exports, booking tools), turns them into event specs, and writes them to a CalDAV calendar or to a local directory of `.ics` files.

Writing to your calendar is routine tracking only when you have agreed to it. The connector never sends a message on your behalf: written events carry no `ORGANIZER` or `ATTENDEE`, so the calendar server sends no invitations or replies. Building an RSVP reply is a separate command, and sending it needs your explicit confirmation.

## Choose a backend

| Kind | Use |
| --- | --- |
| `caldav` | Any CalDAV server (iCloud, Fastmail, Nextcloud, Radicale, and others). Uses only the standard library. |
| `icsdir` | Offline: one folder per calendar under a root-relative `path`, one `.ics` file per event. Good for trials and tests. |
| Plugin | Any other provider through the `jobtracker.calendars` entry point. See the [calendar connector guide](../connectors/writing-a-calendar-connector.md). |

## Configure

Add a `[calendar]` table to ignored `config/jobsearch.toml`:

```toml
[calendar]
kind = "caldav"
url = "https://caldav.example.com/"   # discovery root; or set calendar_url to skip discovery
calendar = "Interviews"
default_timezone = "Europe/London"    # display zone and the zone for floating times
alarms_minutes = [60, 15]
cancel_prefix = "Cancelled: "
```

Put the credentials in ignored `.env`. The variable names are configurable with `user_env` and `password_env`:

```bash
JOBTRACKER_CALDAV_USER=person@example.com
JOBTRACKER_CALDAV_PASSWORD=<app-password>
JOBTRACKER_CALENDAR_SELF_EMAILS=person@example.com
```

Use an app-specific password where the provider offers one. `JOBTRACKER_CALENDAR_SELF_EMAILS` lists your own addresses (comma-separated) so the parser can tell your attendee entry from the other participants. `JOBTRACKER_IMAP_USER`, `JOBTRACKER_SMTP_USER`, and `JOBTRACKER_SMTP_FROM` are also treated as yours.

Check the setup, then list the calendars the account can see:

```bash
.venv/bin/python -m jobtracker doctor
.venv/bin/python -m jobtracker calendar calendars
```

For an offline trial, use `kind = "icsdir"` with `path = "outputs/calendar"`.

## Commands

All commands accept `--root`, `--config`, and `--calendar NAME`.

| Command | Use |
| --- | --- |
| `calendar calendars` | List calendars (read-only). |
| `calendar list [--from --to --grep --managed-only --json]` | Events in a window (default: 30 days back to 90 ahead). `M` = managed by this tool, `R` = recurring. |
| `calendar parse --imap FOLDER:UID \| --eml FILE \| --ics FILE [--out spec.json]` | Read a message (read-only), extract every `.ics`, classify it, and print event specs. Mail without `.ics` gets a `suggested_action`, the meeting links found, and the text. |
| `calendar apply SPEC.json \| --ics FILE [--dry-run]` | Create, update, cancel, or delete from a spec (one object, a list, or `parse` output). |
| `calendar update --key K [--start --end --timezone --title --meeting-url --location --notes-append --evidence --reconfirm]` | Patch one managed event. A new `--start` keeps the duration and clears a cancellation. |
| `calendar cancel --key K --reason R --evidence E` | Mark as cancelled: title prefix, `STATUS:CANCELLED`, alarms removed, reason in the notes. |
| `calendar delete --key K --yes` | Remove for good. Only when you ask for it. |
| `calendar export --key K [--format json\|ics]` | The stored spec or the raw iCalendar. Edit the JSON and `apply` it for larger changes. |
| `calendar reply --ics FILE --partstat ACCEPTED\|DECLINED\|TENTATIVE [--out FILE]` | Build an iTIP REPLY. `--send --confirm-send` mails it through the configured SMTP outbox. |

```bash
.venv/bin/python -m jobtracker calendar parse --imap Jobs:1234 --out outputs/calendar/spec.json
.venv/bin/python -m jobtracker calendar apply outputs/calendar/spec.json --dry-run
.venv/bin/python -m jobtracker calendar apply outputs/calendar/spec.json
```

Keys identify events: `invite:<UID>` for events from an invite (the calendar object keeps the invite UID, so later updates and cancellations match), `manual:<company>:<stage>-<date>` for events from text-only mail, and `ics:<hash>` when the sender's UID is not unique. `--uid` works as well.

## From an e-mail to the calendar

1. Run `calendar parse` for every interview-related message, oldest first.
2. Act on the result:

| What came | `parse` result | Action |
| --- | --- | --- |
| Invite or updated invite | spec `upsert`, method `REQUEST` | `apply`. A later invite with a higher `SEQUENCE` (or the same one with a newer `DTSTAMP`) updates the event; an older one is skipped as `stale`. |
| Cancelled event | spec `cancel`, method `CANCEL` | `apply`: marks the event cancelled and keeps it. |
| ATS confirmation with `.ics` but no `METHOD` | `upsert`, method `NONE` | `apply`. A reschedule often comes with a new UID: cancel the old event by key, then apply the new one. |
| Your own `Accepted:` notices, iTIP `REPLY` | `ignore` | Nothing. |
| Text-only confirmation | `manual_spec` | Copy [`event.json`](../../profile/templates/generic/calendar/event.json) to an ignored path, fill it from the text, and `apply`. |
| Text-only cancellation | `cancel_existing` | `calendar cancel --key ... --reason ... --evidence ...` or [`cancel.json`](../../profile/templates/generic/calendar/cancel.json). |
| Text-only reschedule | `reschedule` | `calendar update --key ... --start ...` or [`update.json`](../../profile/templates/generic/calendar/update.json). |
| Availability request or booking link | `reply_to_recruiter` | No event yet. The reply is yours to send. |
| Reminder | `verify_existing` | `calendar list --grep <company>`: check the event exists and its time matches. |

3. If you track interviews in the store or CRM, copy the `apply` result (start time, status, evidence) to the interview record so both stay in step.

Text-only classification uses English keywords. Add patterns for other languages under `[calendar.text_rules]`, for example `cancel_existing = ["annulé"]`. The keys are the action names in the table above.

## Rules the tool enforces

- Written events never contain `ORGANIZER` or `ATTENDEE`. The organizer and participants go into the notes.
- Times are stored in UTC. Windows zone names (`Romance Standard Time` and others) and custom `VTIMEZONE` blocks are resolved first. Floating times and unknown zones use `default_timezone` and are marked `timezone_confirmed: false` with a note in the event.
- Only events with `X-JOBSEARCH-KEY` are changed. If an invite matches an event you created or accepted yourself, the result is `unmanaged` and nothing happens; rerun with `--allow-unmanaged` only after you decide to hand it over.
- Cancelling keeps the event; deleting needs `--yes`. Re-applying the same spec returns `unchanged` and writes nothing.
- Every write is verified by reading the event back (`"verified": true`).
- Notes end with `— jobsearch: managed event; key=...`, followed by a short change history and the source evidence.
- Updates to one occurrence of a recurring series (`RECURRENCE-ID`) return `manual`; handle them in the calendar app.
- Some servers reject a CalDAV UID filter (HTTP 412). Lookup therefore uses a direct GET of the object, then a time window around the expected start, then a full scan of the calendar.

Revoke access by deleting the app-specific password at the provider and removing the `.env` entries.

# Public contracts

The machine-readable schemas under `schemas/` and the connector API in this directory are the compatibility boundaries for automations, plugins, configuration, stores, and agent workflows.

Current frozen contracts:

- `CFG-V1`: `schemas/jobsearch-config.v1.schema.json` and `schemas/profile-config.v1.schema.json`
- `PAYLOAD-V1`: `schemas/automation-payload.v1.schema.json`
- `CONNECTOR-V1` and `STORE-V1`: `Docs/contracts/connector-api-v1.md`
- `DOCTOR-V1`: `schemas/doctor-report.v1.schema.json`

`CFG-V1` amendment 1 adds the optional `[calendar]` table; `CONNECTOR-V1` amendment 1 adds the optional `jobtracker.calendars` group. Both are backward compatible: existing configs and connectors are unaffected.

Do not change a frozen contract without updating its version or documenting a backward-compatible amendment and refreshing every dependent test and guide.

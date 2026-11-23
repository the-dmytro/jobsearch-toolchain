# Setup notes

Verified facts about setting up this project, shared by every environment. Agents
read this file before probing and add what they verify. Copy it to
`config/setup-notes.md` in a private repository or branch (the public toolchain
ignores that path).

Rules:

- Facts only, each with a date and how it was verified. Mark guesses as open questions.
- Never write secret values, connection strings or keys. Name variables instead.
- Environment-specific choices (such as the connector) stay in that environment's
  variables. Here, record what was observed there so the next agent can propose
  realistic options faster.

## Database

- Backend and hosting: <as declared in config/jobsearch.toml, plus who confirmed it>
- Schema: <latest applied migration and how it was checked>
- Connectors known to work, and where: <connector — kind of environment — date — evidence>

## Environments seen

| Kind of environment | Observed network and tools | Connector chosen | Date |
| --- | --- | --- | --- |
| <for example: own computer, a hosted agent sandbox, a VPS> | <for example: raw TCP blocked, HTTPS through a proxy, a database MCP tool available to the agent> | <connector> | <YYYY-MM-DD> |

## Open questions

- <what the next agent should ask or verify>

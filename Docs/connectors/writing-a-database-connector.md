# Writing a database connector (DB-CONNECTOR-V1)

A database connector is one way to reach one kind of database. The PostgreSQL store,
automation state, documents and migrations all use the connection it returns, so a
new connector makes the whole toolchain work in an environment that the built-in
connectors cannot reach.

Choose the right extension point first:

| You need | Write |
| --- | --- |
| The same SQL database, reached another way (another provider's HTTP API, a proxy, an SSH tunnel, an MCP server over HTTP) | a **database connector** (this page) |
| A different data model or SQL dialect (MySQL, SQLite variants, a document store) | a **store** ([store guide](writing-a-store.md)) plus its migrations; it may use its own connectors |

## Contract

```python
from contextlib import contextmanager
from jobtracker.store.connectors import ConnectorInfo, ProbeResult


class ExampleConnector:
    info = ConnectorInfo(
        name="example_https",          # value of [store] connector
        dialect="postgres",            # the store dialect it serves
        network="https",               # what must be reachable: "postgres_wire", "https", ...
        hosting="example",             # "any" for a generic protocol, else the provider
        transactional=False,           # whether transaction() is atomic
        settings=("EXAMPLE_URL", "EXAMPLE_TOKEN"),   # variable names it reads
        secrets=("EXAMPLE_TOKEN",),                   # the subset that is secret
        description="Example provider's SQL-over-HTTPS endpoint.",
    )

    @contextmanager
    def connect(self, options):
        ...  # yield a ConnectionLike object

    def target(self, options) -> str:
        ...  # host or endpoint for receipts, never credentials

    def probe(self, options, *, timeout: float) -> ProbeResult:
        ...  # non-destructive check: available | reachable | blocked | not_configured | error
```

The connection must provide the subset of DB-API that stores use:

- `cursor()` usable as a context manager, with `execute(sql, params)`,
  `fetchone()` / `fetchall()` returning **dicts**, and `rowcount`;
- `%s` positional placeholders (psycopg style); `params=None` means no substitution;
- `transaction()` context manager, `commit()`, `rollback()`;
- errors raised, never swallowed. Raise `jobtracker.db.MissingConfigurationError`
  for missing settings, unreachable endpoints and rejected credentials.

If `transactional` is false, say so in `description`. The toolchain's writes are
idempotent and read back, so a failure midway is repaired by rerunning the command.

Rules:

- Read only the settings you declare. Never read another connector's settings and
  never fall back to another connector.
- `probe()` must not write data and must not print secret values.
- Keep provider specifics inside the connector; stores stay provider-neutral.

## Registration

In-tree: register in `jobtracker/store/connectors/registry.py`.
Plugin package: expose an entry point.

```toml
[project.entry-points."jobtracker.db_connectors"]
example_https = "example_connector:ExampleConnector"
```

Select it in each environment that should use it:

```text
JOBTRACKER_STORE_CONNECTOR=example_https
```

`[store] hosting` in the shared config must be unset, `any`-compatible, or equal to
the connector's `hosting`.

## Verification

1. `jobtracker probe-environment --format text` lists the connector with its status.
2. Run the store test suite against it. `tests/test_https_sql.py` shows the pattern:
   it serves the connector's endpoint from a local test server backed by a real
   PostgreSQL test database and runs upsert, readback, documents, applications and
   automation state through the connection.
3. `jobtracker doctor` with `JOBTRACKER_STORE_CONNECTOR` set to your connector.

## Blueprints

**Another provider's SQL-over-HTTPS API** (Neon serverless driver endpoint, a
PostgREST RPC gateway on any host): copy `supabase_https.py` and `https_sql.py`.
Keep client-side literal rendering and the `rows` / `exec` statement modes; replace
the endpoint, authentication header and error mapping.

**Generic PostgREST gateway (self-hosted)**: migration `008` works on any PostgreSQL
behind PostgREST. Use `hosting = "any"` and read the gateway URL and token from your
own settings.

**MCP server over HTTP**: some providers expose an MCP server with an `execute_sql`
tool (for example Supabase's hosted MCP server, scoped with `project_ref`). A
connector can be an MCP client that sends each statement as a tool call. Decide with
the user first: such servers often need an account-wide access token, which is
broader than a project key, and may rate-limit. Scope the server to one project and
never enable write access beyond what the toolchain needs.

**SSH tunnel or bastion**: open the tunnel inside `connect()` and delegate to
psycopg; declare `network = "ssh"` so probes and agents can tell it apart.

**A different database (MySQL, …)**: write a store for that dialect with its own
migrations and connectors whose `dialect` matches it. Do not translate PostgreSQL
SQL inside a connector.

# Writing a store connector

Stores persist automation payloads and artifacts.

## Built-in backends

| Backend | Config | Use case |
|---------|--------|----------|
| `postgres` | `JOBTRACKER_DATABASE_URL` | Production (Supabase, RDS, local) |
| `sqlite` | `store.sqlite_path` | Zero-config local dev |
| `memory` | — | Tests, `--dry-run` |

**`config/jobsearch.toml`:**

```toml
[store]
backend = "postgres"
artifact_backend = "local"
artifact_local_path = "outputs/artifacts"
```

## JobStore protocol

```python
class JobStore(Protocol):
    def upsert_run(self, payload: RunPayload) -> UpsertResult: ...
    def check_duplicates(self, provider: str, external_id: str) -> list[DuplicateMatch]: ...
    def known_refs(self, provider: str) -> frozenset[str]: ...
    def migrate(self) -> list[str]: ...
```

Postgres implementation: `jobtracker/store/generic/postgres.py` (SQL from original `payloads.py`).

## Artifact stores

| Backend | Env / config |
|---------|----------------|
| `local` | `artifact_local_path` |
| `s3` | `AWS_*` or compatible endpoint |
| `supabase-storage` | `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_STORAGE_BUCKET` |

## Custom store (out-of-tree)

```toml
[project.entry-points."jobtracker.stores"]
mydb = "my_store_plugin.postgres:MyPostgresStore"
```

```python
from jobtracker.store.base import JobStore, UpsertResult

class MyPostgresStore:
  def upsert_run(self, payload):
    # implement against your schema or adapt payload mapping
    return UpsertResult(run_id="...", created=True)
```

Register in config:

```toml
[store]
backend = "mydb"
```

## Migrations

SQL migrations live in `db/migrations/`. Apply with:

```bash
python -m jobtracker migrate
python -m jobtracker migrate --dry-run   # list pending
```

Migration tracking is by **filename** — safe to edit applied migrations only if you understand downstream impact.

## Testing

Use `MemoryJobStore` from `jobtracker/store/generic/memory.py`:

```python
from jobtracker.store.generic.memory import MemoryJobStore

store = MemoryJobStore()
result = store.upsert_run(payload_dict)
assert result.created
```

See `tests/test_connector_contract.py`.

# Test-data policy

All people, roles, locations, compensation, companies, messages, credentials, and
identifiers in this directory are fictitious regression data. Reserved domains are
used wherever the value is not specifically testing public-safety rejection. Test
fixtures must never be copied into a user's private profile.

## Hermetic runs

Tests must pass with and without a real `config/jobsearch.toml`, `.env` and
`JOBTRACKER_*`/`SUPABASE_*` variables. A module that relies on default config or
environment lookup installs `set_up_module`/`tear_down_module` from `tests/hermetic.py`,
which switches to an empty temporary working directory and project root and clears those
variables; CLI subprocess tests use `hermetic.subprocess_kwargs()`.

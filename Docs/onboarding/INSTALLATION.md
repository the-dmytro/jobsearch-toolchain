# Installation

Standard support is macOS and Linux with Python 3.10 or newer. Docker, Node.js, PostgreSQL, and Supabase are not required for the core.

```bash
git clone https://github.com/the-dmytro/jobsearch-toolchain.git
cd jobsearch-toolchain
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m jobtracker benchmark-sources \
  --providers example_jsonld \
  --fixture-dir jobtracker/fixtures/provider_fetch
```

Use the activation command for convenience if desired, but documentation keeps explicit `.venv/bin/` paths so the selected interpreter is clear.

For development, also run `.venv/bin/pip install -r requirements-dev.txt`. Install
optional capabilities only when selected: `-e '.[postgres]'`, `-e '.[supabase]'`, or
`-e '.[legacy-import]'`. The project makes no Windows support claim in v0.2.0.

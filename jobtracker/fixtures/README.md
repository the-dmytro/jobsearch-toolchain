# Fictitious regression fixtures

Everything in this directory is deterministic test data. Names, roles, locations,
compensation, message text, company associations, and identifiers are fictitious or
adapted solely to exercise connector parsers; none describes a toolchain user.

`provider_targets.toml` is deliberately broad and neutral. It exists for the offline
benchmark aliases and must never be treated as a private search profile. New examples
belong under `examples/`; new parser regressions may be added here with stable IDs and
without personal facts or credentials.

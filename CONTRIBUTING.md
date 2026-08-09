# Contributing

Create reusable changes in a branch of the public repository and open a pull request. Install development tools with `requirements-dev.txt`.

Changes to schemas, connector signatures, store behavior, doctor semantics, migrations, fixtures, examples, or compatibility require matching tests and documentation. Breaking public-contract changes require a new contract version; do not silently edit v1 semantics.

Never commit personal data or secrets. Use reserved example domains and explicitly fictitious fixtures. Run the release checklist gates relevant to the change before requesting review.

Out-of-tree connectors should be installed from a local path or Git URL. The host package is not advertised as a PyPI dependency in v0.2.0.

Private emergency fixes must carry an upstream issue or PR reference and be generalized before publication. See [PUBLIC_UPSTREAM.md](Docs/contributing/PUBLIC_UPSTREAM.md).

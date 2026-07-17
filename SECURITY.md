# Security Policy

## Scope and trust model

The published static case runs on committed, deterministic synthetic files and
does not require credentials. The repository also contains optional production
paths for vendor ingestion, dbt/PostgreSQL transformation, signed alert
webhooks, and an authenticated aggregate FastAPI service. Those paths are
fail-closed when required environment configuration is absent.

The relevant attack surface is therefore:

- Python packages and GitHub Actions used to build and test the project;
- workflow permissions and release configuration;
- local HTML/PDF rendering through a headless browser;
- OAuth, API, billing, database, dashboard, and webhook credentials supplied by
  the deployment environment;
- untrusted vendor JSON normalized by the source adapters;
- Basic and API-key authentication, aggregate query filters, and small-cell
  disclosure risk; and
- files supplied by a developer who deliberately replaces governed inputs.

The adapters minimize vendor payloads before persistence and block malformed
contracts. The API publishes only server-side aggregates, suppresses cells below
10 customers, uses constant-time credential checks and explicit scopes, and
does not cache responses. These controls do not make arbitrary personal data
anonymous. Production use still requires organizational identity, retention,
access, privacy, network, and incident controls. See
[docs/PRIVACY.md](docs/PRIVACY.md), [docs/API.md](docs/API.md), and
[docs/INGESTION.md](docs/INGESTION.md).

## Supported versions

Only the latest tagged release on `main` is supported. See
[CHANGELOG.md](CHANGELOG.md).

## Reporting a vulnerability

Private vulnerability reporting is not currently enabled for this repository,
and this policy does not advertise an unverified email address. Until a private
channel is configured, open a GitHub issue containing only a request for private
security contact. Do **not** include exploit details, secrets, proof-of-concept
payloads, or affected data in that public issue. The maintainer can then arrange
a private follow-up channel.

Repository administrator action required: enable GitHub **Private vulnerability
reporting** under repository security settings. Once enabled, this section should
link directly to the repository's private advisory form and the public-contact
fallback can be removed.

## Automated safeguards

- **Dependency audit** — every push and pull request runs `pip-audit` against the
  declared runtime and development requirements
  ([CI workflow](.github/workflows/ci.yml)).
- **Static analysis** — [CodeQL](.github/workflows/codeql.yml) analyzes Python on
  pushes and pull requests to `main` and on a weekly schedule.
- **Dependency updates** — [Dependabot](.github/dependabot.yml) proposes updates
  for Python packages and GitHub Actions weekly.
- **Least-privilege CI** — the standard CI workflow grants its `GITHUB_TOKEN`
  read-only repository contents access; release permissions are declared in the
  separate release workflow.
- **Credential isolation** — adapters, API authentication, PostgreSQL, and alert
  signing read secrets only from environment variables; manifests and logs
  contain provenance and error types, not secret values or vendor bodies.
- **Authenticated publication** — live dashboard access uses same-origin Basic
  authentication; API keys are configured as SHA-256 digests with explicit
  scopes. Deployment requires TLS.
- **Privacy gate** — aggregate dashboard queries enforce a minimum cell size and
  final QA rejects identifier-bearing API snapshots.

These controls reduce risk but do not replace review of open alerts or repository
security settings.

## Dependency reproducibility

The complete runtime and development dependency closure in `requirements.txt`
and `requirements-dev.txt` uses exact version pins, and GitHub Actions are
commit-pinned. Python package artifacts are not hash-locked, so a fresh
environment is not a byte-for-byte reproducible software supply chain. CI audits
the resolved environment; production hardening should add reviewed hashes and a
controlled process for automated pin updates.

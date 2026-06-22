# Security Policy

## Scope

This is a self-contained analytics pipeline. It generates **synthetic** data and
writes local artifacts. It has no network calls at runtime, no authentication, no
secrets, and no user-supplied input. The realistic attack surface is therefore
limited to the third-party Python dependencies and the CI workflows.

## Supported versions

The latest tagged release on `main` is supported. See [CHANGELOG.md](CHANGELOG.md).

## Reporting a vulnerability

If you find a security issue — most plausibly in a pinned dependency or a CI
configuration — please report it privately via GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, or by email to the maintainer listed on the GitHub profile.
Please do not open a public issue for an unfixed vulnerability.

You can expect an acknowledgement within a few days.

## Automated safeguards

- **Dependency audit** — every push and pull request runs `pip-audit` against the
  pinned runtime and dev requirements ([CI workflow](.github/workflows/ci.yml)).
- **Static analysis** — [CodeQL](.github/workflows/codeql.yml) scans the Python
  sources for common vulnerability patterns on push, PR, and a weekly schedule.
- **Dependency updates** — [Dependabot](.github/dependabot.yml) proposes pinned
  upgrades for Python packages and GitHub Actions weekly.
- **Least-privilege CI** — workflow `GITHUB_TOKEN` permissions are scoped to the
  minimum each job needs (`contents: read` for CI).

## Dependencies

All dependencies are version-pinned in `requirements.txt` (runtime) and
`requirements-dev.txt` (tooling) so builds are reproducible and auditable.

# Security policy

## Supported versions

Security fixes target the latest published 0.x release. Older versions are not
separately maintained. Report a problem even if it affects an older version;
upgrade guidance or mitigation will depend on the finding. This volunteer
project does not promise a fixed response or remediation deadline.

Palgwae reads repositories and emits portable graph bundles. Treat those
bundles as potentially sensitive because paths, names, and dependencies may
reveal architecture.

## Dependency maintenance

Palgwae uses a security-only dependency update policy. Routine version-update
pull requests are disabled; Dependabot alerts and security-update pull requests
are enabled in repository settings for supported dependencies. The configuration
covers GitHub Actions, the root Python environment, the optional Graphify
integration, and the separately locked plugin runtime. The weekly schedule in
the configuration does not delay security updates.

Security updates still require review and passing checks; they are not
automatically merged. Dependency upgrades for features, compatibility, or
end-of-life support are reviewed when preparing a release or resuming active
development. This policy reduces routine maintenance noise, but does not
guarantee that every vulnerability is detected or can be fixed automatically.

GitHub does not generate Dependabot alerts for SHA-pinned Actions, which this
repository uses. Review their upstream security advisories during maintenance;
do not replace immutable pins merely to enable alerts. See GitHub's
[dependency graph coverage](https://docs.github.com/en/code-security/reference/supply-chain-security/dependency-graph-supported-package-ecosystems).
When a Python security fix changes a shared direct dependency, update the root
and plugin runtime manifests together and regenerate both affected lockfiles;
their dependency constraints must remain aligned.

## Before sharing a bundle

- remove credentials and environment payloads;
- use repository-relative paths;
- exclude source excerpts unless their license permits redistribution;
- scan for home-directory and temporary paths;
- review runtime metadata for tenant or customer identifiers;
- verify every file listed in the manifest.

## Reporting a vulnerability

Report suspected vulnerabilities through
[GitHub's private vulnerability reporting form](https://github.com/yonghyeokrhee/Palgwae/security/advisories/new).
Do not publish exploit details in a public issue.

The MCP server is read-only and permits only loopback HTTP binding. The CLI
rejects other interfaces. It does not implement multi-tenant authentication.
Do not expose private bundles through an unauthenticated proxy. A public
ChatGPT integration needs a separately designed authenticated deployment.

## Trust boundaries

The Airflow adapter parses Python syntax without importing DAGs or calling
Airflow, cloud APIs, SQL engines, or user functions. It verifies a limited set
of declared control relationships. It cannot establish that a DAG imports
successfully, that a task ran, or that an operator writes a particular dataset.

Bundle hashes detect a change relative to a manifest; they are not signatures
or proof of the author's identity. Replacing a bundle and its manifest together
requires a separate trust decision. Source updates require a new extraction.

Local CLI analysis sends no telemetry or source uploads. Installation and uv
environment setup may contact package registries. MCP returns graph metadata
to the client you connect, which may send it to its model provider. Graphify
remains an optional, separately installed extraction process. See
[privacy documentation](docs/privacy.md).

# Security policy

## Supported versions

Security fixes target the latest published 0.x release. Older versions are not
separately maintained. Report a problem even if it affects an older version;
upgrade guidance or mitigation will depend on the finding. This volunteer
project does not promise a fixed response or remediation deadline.

Palgwae reads repositories and emits portable graph bundles. Treat those
bundles as potentially sensitive because paths, names, and dependencies may
reveal architecture.

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

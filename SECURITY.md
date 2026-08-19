# Security policy

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

The MCP server is read-only and binds HTTP to `127.0.0.1` by default. Exposing
it on another interface requires an explicit user decision and appropriate
authentication outside the scope of this alpha release.

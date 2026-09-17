# Changelog

## 0.3.0 — Airflow source ingestion (2026-09-07)

- Extract declared Airflow DAGs, literal operator/sensor tasks, basic TaskFlow
  calls, dependency chains, and locally resolvable ExternalTaskSensor targets.
- Keep dynamic construction and unsupported patterns as explicit unresolved
  records. DAG source is parsed, never imported or executed.
- Add `example`, `init`, and `airflow` commands. The fictional Airflow example
  ships in the wheel and does not require an Airflow installation.
- Add a Claude Code marketplace and an npm-compatible launcher bundling the
  Python wheel, usable with npm, pnpm, or Bun. Requires uv.
- Document local ChatGPT/Codex plugin packaging and remote ChatGPT connection
  requirements. No hosted MCP service or public directory listing is implied.
- Add installed-wheel/MCP checks, optional Graphify CI, release artifacts,
  dependency auditing, CodeQL, and contributor guidance.
- Update the locked cryptography dependency to 50.0.1.

Compatibility: bundle schema remains 1. The new Airflow adapter uses its own
versioned control-flow ontology; the original YAML compiler and retail fixture
remain supported. No migration of existing bundles is required. Source changes
require rebuilding; a bundle is a snapshot, not a live scheduler view.

## 0.2.0

- Added thin Codex, Claude Code, and OpenCode client distributions.
- Added the optional Graphify candidate integration and third-party notices.

## 0.1.0

- Initial evidence-bounded JSONL bundle, CLI, MCP, schemas, and retail fixture.

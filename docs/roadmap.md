# Palgwae's small roadmap

Palgwae should grow through independent adapters and tests, not through a large
platform rewrite.

## 0.1 — portable proof

- [x] evidence-bounded JSONL bundle
- [x] deterministic upstream/downstream/path queries
- [x] CLI and read-only MCP
- [x] fictional end-to-end demo
- [x] bundle integrity and negative `UNKNOWN` tests

## Good first contributions

- [x] inspect a bundle with a dependency-free static HTML view
- [x] distribute the same MCP query contract to Codex, Claude Code, and OpenCode
- [x] quarantine Graphify 0.9.46 as an optional code-only candidate extractor
- [ ] ingest dbt `manifest.json` into candidates
- [ ] ingest OpenLineage events into candidates
- [ ] extract Airflow DAG/task scheduling
- [ ] parse SQL table lineage with a pluggable parser
- [ ] bind Terraform resources to scripts and environments
- [ ] resolve Graphify candidates against an organization-owned canonical registry
- [ ] add AST, SQL, and Terraform predicate-specific promotion verifiers
- [ ] add GitHub Actions artifact publishing
- [ ] document a second demo using Spark and Kafka

## Later, only with evidence

- column-level lineage;
- bitemporal lifecycle snapshots;
- graph-database backends;
- optional embeddings for entity discovery;
- review UI for candidate promotion;
- signed release bundles.

## Non-goals for now

- natural-language answer generation;
- mandatory LLM or embedding calls;
- replacing a data catalog;
- production runtime monitoring;
- automatic lifecycle or cutover decisions;
- write-capable MCP tools.

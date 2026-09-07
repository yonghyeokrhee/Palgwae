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
- [x] extract literal Airflow DAG/tasks, basic TaskFlow, and declared dependency edges
- [ ] parse SQL table lineage with a pluggable parser
- [ ] bind Terraform resources to scripts and environments
- [ ] resolve Graphify candidates against an organization-owned canonical registry
- [ ] add AST, SQL, and Terraform predicate-specific promotion verifiers
- [x] add GitHub Actions artifact publishing and installed-wheel smoke checks
- [ ] document a second demo using Spark and Kafka

## Later, only with evidence

- expand Airflow TaskGroups and repeated TaskFlow calls with explicit compatibility tests;
- verify against serialized DAG exports without scheduling production jobs;
- opt-in authenticated ChatGPT hosting and public plugin-directory submission;
- npm/PyPI registry publication after publisher accounts are configured;

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

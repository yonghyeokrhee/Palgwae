# Prior art and Palgwae's boundary

Palgwae does not claim to invent graph retrieval, metadata catalogs, or data
lineage. It combines a narrow set of ideas for repository-native pipeline
impact analysis across its
[eight context views](eightfold-context-model.md).

## Related projects

- [OpenLineage](https://github.com/OpenLineage/OpenLineage) standardizes
  runtime job, run, and dataset lineage events.
- [Marquez](https://github.com/MarquezProject/marquez) collects and visualizes
  OpenLineage metadata.
- [DataHub](https://github.com/datahub-project/datahub) and
  [OpenMetadata](https://github.com/open-metadata/OpenMetadata) are broad
  metadata, governance, and context platforms with lineage and agent access.
- [dbt MCP](https://github.com/dbt-labs/dbt-mcp) exposes dbt metadata and
  lineage to MCP clients.
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag) builds graph
  structures from unstructured text for retrieval and summarization.
- [LightRAG](https://github.com/HKUDS/LightRAG) combines graph and vector
  retrieval for documents.
- Code graph projects use ASTs and symbol indexes to map calls, imports, and
  types across repositories.

## Palgwae's boundary

Palgwae is intentionally:

- lighter than a metadata platform;
- more pipeline- and contract-aware than a symbol graph;
- more deterministic than LLM-extracted document GraphRAG;
- broader than SQL-only lineage;
- usable as checked-in files without a server backend.

Its distinctive output is not a generated answer. It is a reviewable set of
typed claims whose evidence, environment, scope, and uncertainty survive
retrieval.

The most useful integration strategy is cooperation:

- import runtime lineage from OpenLineage;
- import models and tests from dbt;
- import ownership and schema from a catalog;
- import source-defined control and contract edges from repository adapters;
- publish the resulting portable snapshot through CLI and MCP.

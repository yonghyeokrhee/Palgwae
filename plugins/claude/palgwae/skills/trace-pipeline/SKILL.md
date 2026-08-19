---
name: trace-pipeline
description: Use Palgwae for data-pipeline entity resolution, upstream or downstream traversal, dependency paths, change impact, and claim evidence.
---

# Trace a pipeline with Palgwae

Resolve names with `find_entity` before traversal. Use only canonical IDs for
`get_upstream`, `get_downstream`, `find_dependency_path`, and
`assess_change_impact`. Inspect material claims with `get_claim_evidence` and
include the snapshot ID from `graph_health` when reproducibility matters.

`UNKNOWN` means unproven in the active accepted bundle, not absent. Graphify
candidate output is quarantined build input and is never accepted knowledge.

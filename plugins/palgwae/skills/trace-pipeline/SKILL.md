---
name: trace-pipeline
description: Use Palgwae for data-pipeline entity resolution, upstream or downstream traversal, dependency paths, change impact, and claim evidence.
---

# Trace a pipeline with Palgwae

1. Call `graph_health` first. The plugin bootstraps `.palgwae/bundle` when it
   is missing.
2. If `accepted_claims` is zero, explain that only a fail-closed starter was
   created. Use ordinary source inspection for the current answer and propose
   an evidence-backed `palgwae-context-graph.yaml`; do not treat the starter as
   extracted lineage.
3. Call `find_entity` before using a name in a traversal.
4. Ask the user to choose when more than one canonical entity is a plausible match.
5. Use `get_upstream`, `get_downstream`, or `find_dependency_path` on canonical IDs.
6. Use `assess_change_impact` for a proposed modification.
7. Call `get_claim_evidence` before presenting a material relationship as confirmed.
8. Report the active snapshot ID from `graph_health` when reproducibility matters.

Only accepted, evidence-backed claims participate in traversal. `UNKNOWN` means
the active bundle does not prove the relationship. It is not proof that the
relationship is absent. Candidate extractor output, including Graphify output,
must never be presented as accepted Palgwae knowledge.

Bootstrap writes only project-local state under `.palgwae/` (the bundle and a
first-start lock). If a
conventional `palgwae-context-graph.yaml` (or `.yml`/`.json`) exists, it is
compiled. Otherwise the starter contains one repository node and an explicit
unresolved boundary; it never fabricates pipeline relationships.

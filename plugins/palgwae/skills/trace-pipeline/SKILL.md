---
name: trace-pipeline
description: Use Palgwae for data-pipeline entity resolution, upstream or downstream traversal, dependency paths, change impact, and claim evidence.
---

# Trace a pipeline with Palgwae

1. Call `find_entity` before using a name in a traversal.
2. Ask the user to choose when more than one canonical entity is a plausible match.
3. Use `get_upstream`, `get_downstream`, or `find_dependency_path` on canonical IDs.
4. Use `assess_change_impact` for a proposed modification.
5. Call `get_claim_evidence` before presenting a material relationship as confirmed.
6. Report the active snapshot ID from `graph_health` when reproducibility matters.

Only accepted, evidence-backed claims participate in traversal. `UNKNOWN` means
the active bundle does not prove the relationship. It is not proof that the
relationship is absent. Candidate extractor output, including Graphify output,
must never be presented as accepted Palgwae knowledge.

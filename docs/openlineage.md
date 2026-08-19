# OpenLineage compatibility

OpenLineage and Palgwae solve adjacent problems.

OpenLineage provides a standard event model for jobs, runs, datasets, and
facets. Palgwae provides a portable, evidence-bounded snapshot spanning its
[eight context views](eightfold-context-model.md), including source structure,
control flow, contracts, lifecycle, and cross-repository impact.

An adapter can map:

| OpenLineage | Palgwae graph |
|---|---|
| `Job` | `Job` or `Task` entity |
| `Run` | runtime observation, normally not a durable topology node |
| input dataset | `job READS_FROM dataset` |
| output dataset | `job WRITES_TO dataset` |
| parent/run facets | control-flow candidate |
| schema facet | dataset/column attributes |

Important trust rule: one observed run is evidence for that run. Promoting it to
a durable dependency should follow a project policy, such as repeated
observation plus a matching declared job definition.

The first community adapter should consume exported OpenLineage events and emit
candidate claims. It should not require a running Marquez or DataHub service.

# Palgwae ontology and relation direction

Palgwae's ontology is small on purpose. New types and predicates should be
introduced only when they change a useful query or remove a real ambiguity.

The entity groups and predicates make the
[Eightfold Context Model](eightfold-context-model.md) queryable. The eight
views are an interpretation layer over one typed graph, not eight separate
schemas.

A project spec selects both contracts explicitly:

```yaml
ontology:
  entities: ../../ontology/entities.yaml
  relations: ../../ontology/relations.yaml
```

Both documents declare the same ontology name and version. The builder checks
entity identity fields and relation directions, then records both file hashes
in the portable manifest.

## Entity groups

| Group | Starter types |
|---|---|
| Resource | `Repository`, `Environment`, `Orchestrator`, `Task`, `Job`, `Service`, `Queue`, `Trigger` |
| Data | `LogicalDataset`, `PhysicalDataset`, `Column` |
| Contract | `DataContract`, `MessageContract`, `MarkerContract`, `ArgumentContract`, `Invariant`, `SLA` |
| Evolution | `LifecycleAssertion`, `Decision`, `Migration`, `Incident` |

Adapters may attach platform-specific attributes without creating a new entity
type for every vendor product.

## Direction is part of the contract

| Predicate | Subject → Object | Example |
|---|---|---|
| `SCHEDULES` | scheduler → scheduled task | DAG → task |
| `TRIGGERS` | trigger → target | timer → DAG |
| `STARTS` | controller → execution target | task → batch job |
| `INVOKES` | caller → callee | service → function |
| `ENQUEUES_TO` | producer → queue | function → work queue |
| `CONSUMES` | consumer → contract/queue | worker → work queue |
| `READS_FROM` | consumer → dataset | SQL model → bronze table |
| `WRITES_TO` | producer → dataset | SQL model → silver table |
| `EMITS` | producer → contract/marker | job → DONE marker |
| `REQUIRES` | consumer → contract/invariant | API → freshness contract |
| `OWNED_BY` | resource → repository/team | job → repository |
| `DEPLOYED_IN` | resource → environment | job → production |
| `REPLACES` | successor → predecessor | new job → legacy job |
| `VALIDATED_BY` | claim/resource → decision/evidence | lifecycle → approval |

Traversal code converts these semantic directions into upstream/downstream
paths. It must not reverse individual predicates simply to make a drawing look
convenient.

## Relation selection test

Before adding an edge, ask:

1. Would removing this edge change an impact or dependency answer?
2. Can a reviewer point to evidence that entails exactly this predicate?
3. Is the direction stable across tools?
4. Is this topology, a runtime observation, or lifecycle state?
5. Does the relationship need a contract entity in the middle?

If the answer to 2 is no, keep the candidate unresolved. If the answer to 4 is
unclear, do not merge lifecycle and topology into one edge.

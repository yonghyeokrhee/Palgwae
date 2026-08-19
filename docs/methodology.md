# Palgwae methodology

Palgwae models a data engineering estate as a set of testable claims, not as a
collection of generated prose. Its
[Eightfold Context Model](eightfold-context-model.md) keeps data flow, control
flow, infrastructure, contracts, runtime state, lifecycle, cross-repository
ownership, and evidence/trust visible in the same graph.

## 1. Separate entities, claims, and evidence

An entity is a canonical thing: a job, dataset, queue, repository, contract, or
environment. A claim is a directed relationship between two entities. Evidence
is the reproducible source that supports a claim.

```text
entity -- claim(predicate) --> entity
              |
              +--> one or more evidence records
```

This split prevents a common graph failure: storing a plausible relationship
without retaining how it was learned.

## 2. Canonical identity before traversal

Names are not identities. `orders_daily` may be a table in three environments,
a job, or a dashboard. Adapters must produce stable IDs that include the
identity fields needed to disambiguate the entity.

The bundled fictional fixtures use:

```text
urn:example:palgwae:<scope>:<entity-type>:<qualified-name>
```

`urn:example` is the registered example namespace and is fixture-only. A real
adapter **MUST** use a canonical URI namespace controlled by the deploying
organization; it must not emit `urn:example` identifiers for production
entities. The exact organization-controlled syntax is less important than
determinism. Rebuilding the same source at the same revision must produce the
same ID.

## 3. Model all eight views, not only code

A useful impact path frequently crosses categories:

| View | Examples |
|---|---|
| Data flow | reads, writes, transforms, materializes |
| Control flow | schedules, triggers, starts, invokes, queues |
| Infrastructure | deployment environments, queues, physical resources |
| Contracts | emits, consumes, requires, gates |
| Runtime state | observed runs and time-bounded activity |
| Lifecycle | authority, replacement, migration, retirement, incident |
| Cross-repository ownership | repositories, services, and teams |
| Evidence and trust | source locators, revisions, review state, unresolved gaps |

The graph is intentionally able to express a path such as:

```text
Airflow DAG
  -> schedules task
  -> starts batch job
  -> writes Iceberg table
  -> emits DONE marker
  -> gates prediction service
```

A plain SQL lineage graph cannot answer the final two steps. A code-call graph
usually cannot answer the dataset step. The other views establish where the
path runs, who owns it, whether it is current, and why each edge should be
trusted.

## 4. Edge acceptance rubric

An adapter may emit candidates freely. A candidate becomes an accepted claim
only when all gates pass:

1. subject and object resolve to canonical entities;
2. the predicate exists in the ontology;
3. direction follows the predicate contract;
4. at least one evidence record is pinned;
5. an auto-verified source locator resolves to the cited line range;
6. the evidence entails the relationship at the declared scope;
7. environment and repository bindings do not conflict;
8. the claim is not marked inferred-only or superseded.

Suggested evidence levels:

| Level | Evidence | Default handling |
|---|---|---|
| A | exact source/config/SQL locator at a revision | auto-verifiable |
| B | structured runtime metadata | accepted for observation; dependency still scoped |
| C | design document or runbook | candidate unless corroborated |
| D | naming convention or model inference | unresolved |

Runtime activity proves that something ran. It does not, by itself, prove that a
specific downstream dependency exists. Documentation explains intent and
history. It does not override current source.

The starter builder auto-verifies exact `L12` or `L12-L18` locators. Symbolic
locators remain candidates unless a deterministic adapter resolves them or a
human approves them.

## 5. Preserve `UNKNOWN`

Absence of an accepted path has three possible meanings:

- the dependency does not exist;
- the extractor does not support that source;
- evidence exists but has not been reviewed or promoted.

The graph cannot safely distinguish those cases without more evidence. Query
tools therefore return `UNKNOWN`, with an unresolved boundary when available.
Agents must not rewrite it as "no dependency."

## 6. Keep lifecycle separate from topology

Declared, deployed, recently observed, paused, retired, and authoritative are
different facts. A resource can still exist in source after retirement, or run
occasionally while no longer being the authoritative writer.

Lifecycle promotion should require explicit policy or human review. Time-bound
runtime observations should remain observations unless a policy defines how
they map to lifecycle.

## 7. Build immutable, portable snapshots

A distributable bundle contains only graph artifacts and reproducible
provenance. Its manifest hashes every file, records every evidence source
revision, and binds the snapshot to entity and relation ontology hashes.

The runtime:

- starts without source repositories or cloud credentials;
- fails closed when a hash changes;
- exposes the snapshot ID in every health response;
- remains read-only.

This makes two developers—and two different agents—query the same accepted
knowledge instead of rebuilding an implicit graph on every machine.

## 8. Golden questions are executable contracts

Each project should maintain a compact Golden set that includes:

- name resolution;
- one direct upstream and downstream path;
- one cross-repository path;
- one contract or marker path;
- one negative question that must return `UNKNOWN`;
- claim evidence with revision, path, and locator;
- a known lifecycle decision.

Golden tests should compare structured results, ignoring transport metadata and
JSON key order. Do not evaluate only natural-language answers.

## 9. Automation versus human decisions

Agents and adapters can:

- inventory source and configuration;
- normalize entities;
- extract candidate edges;
- compute hashes and revisions;
- detect conflicts and missing endpoints;
- execute Golden tests;
- show a review queue.

Humans should decide:

- ambiguous name bindings;
- whether a legacy route is retired or merely quiet;
- authoritative writer and source-of-truth changes;
- contract semantics hidden behind shared marker names;
- cutover and coexistence state;
- whether documentation-only evidence is sufficient.

The goal is not zero human review. It is to make the review surface finite,
evidence-rich, and repeatable.

## 10. Adapter contract

An adapter should emit candidates, not write directly into accepted graph
files. Its output must include:

```yaml
subject: urn:example:palgwae:...
predicate: WRITES_TO
object: urn:example:palgwae:...
scope:
  repository: example
  revision: full-revision
evidence:
  path: sql/orders.sql
  locator: L12-L18
  content_hash: sha256:...
```

Promotion is a separate deterministic stage. This boundary makes it possible to
add parsers without silently changing graph truth.

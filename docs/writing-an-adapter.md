# Writing an adapter

Adapters translate one source format into candidate entities, claims, evidence,
and unresolved boundaries.

## Contract

An adapter should be:

- deterministic for the same input and revision;
- read-only;
- explicit about its supported versions and dialects;
- conservative around dynamic values;
- independent from promotion policy.

It must never mark a claim accepted solely because a name looks familiar.

Adapter configuration **MUST** provide a canonical URI namespace controlled by
the deploying organization. The repository's `urn:example:palgwae:*` IDs are
only for fictional fixtures and must never be copied into a real graph.

## Suggested interface

```python
class Adapter:
    name = "example"
    version = "1"

    def extract(self, source_root, config):
        return ExtractionResult(
            nodes=[],
            candidate_claims=[],
            evidence=[],
            unresolved=[],
        )
```

Each candidate should retain the source-native fact that produced it. For
example, a SQL adapter may know that a token appeared in `FROM`, while a
Terraform adapter may know that one resource attribute references another.
Promotion can then decide whether that fact entails `READS_FROM`, `STARTS`, or
another ontology predicate.

## Dynamic targets

If the target is assembled from a variable, secret, environment lookup, plugin,
or runtime payload, emit an unresolved boundary:

```yaml
source_node_id: urn:example:palgwae:example:job:publisher
target_hint: notification_target
reason: Target is supplied at deployment time.
evidence_ids: [evidence:...]
```

Do not fabricate a target node to complete the path.

## Test fixture

Every adapter contribution should contain:

1. a minimal public or synthetic source;
2. expected entities and candidate claims;
3. at least one unsupported/dynamic case;
4. a deterministic rebuild assertion;
5. a Golden query affected by the adapter.

## Candidate adapters

Useful narrow adapters include:

- OpenLineage event export;
- dbt `manifest.json`;
- Airflow DAG and task metadata;
- Dagster assets and jobs;
- Terraform references;
- SQL table lineage;
- Kafka topic producers/consumers.

Prefer a small adapter with a documented trust boundary over broad parsing with
unclear false-positive behavior.

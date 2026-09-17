# Validation and limits

On 2026-09-07 the adapter was exercised locally against an existing private
data-engineering repository with its owner's permission. No private source,
repository name, task identifier, bundle, or excerpt is in the public fixtures.

| Observed result | Count |
| --- | ---: |
| Python files scanned | 27 |
| Files importing Airflow | 26 |
| Statically identified DAGs | 26 |
| Statically identified tasks | 99 |
| Task membership claims | 99 |
| Within-DAG NEXT claims | 78 |
| Resolved cross-DAG WAITS_FOR claims | 7 |
| Unresolved records | 38 |
| Verified evidence records | 158 |

Two extractions produced identical bundle digests. All 85 accepted dependency
edges were exercised as forward queries. Each retained evidence record matched
the normalized source bytes and line bounds. These checks establish consistency
and reproducibility, not independently measured precision or recall. No
scheduler or task was executed.

Unresolved records comprised 20 repeated TaskFlow identities, eight unresolved
dependency endpoints, nine conditional/loop/exception-controlled regions, and
one dynamic identity or unsupported membership. Tasks may also be hidden inside
arbitrary helpers. An unresolved count is not a completeness score.

The public `palgwae example` fixture covers classic DAGs, fan-out, a cross-DAG
sensor, and TaskFlow. Tests cover supported and negative cases. The installed
wheel smoke test runs outside the checkout and exercises example creation,
extraction, cross-DAG queries, and MCP.

Run `scripts/validate_airflow_repository.py` on a permitted local source directory
for the same aggregate checks. No private checkout is needed for CI.

Unvalidated: exhaustive Airflow/provider compatibility, runtime importability,
dynamic expansion, TaskGroups, Spark/SQL lineage, model answer quality, token
savings, and interactive installation in every host. Public directory approval
is also separate. This exercise supports no percentage accuracy, productivity,
or production-readiness claim.

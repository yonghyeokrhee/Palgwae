# Airflow: from source to an explainable change impact

If `publish` changes, which scheduled tasks depend on it, and where is each
dependency declared? Palgwae reads a DAG source directory and makes those
declarations queryable through a local CLI or an agent's MCP tools.

```sh
palgwae init --source ./dags --namespace https://example.org/engineering/pipelines
palgwae find publish --bundle .palgwae/bundle
```

Use a URI namespace your organization controls for real inputs. The namespace
forms graph IDs; no request is made to that URL. Pass a source directory for one
deployment. Reusing the same `dag_id` across staging and production requires
separate source roots and namespaces.

Copy an ID returned by `find` into `downstream`, `upstream`, or `impact`. Then
inspect claim evidence through MCP. Re-run `palgwae airflow ./dags --namespace
…` after editing sources. `doctor` verifies a bundle's internal integrity; it
does not compare that snapshot with the current working tree.

## Supported declarations

| Input | What becomes accepted | Boundary |
| --- | --- | --- |
| `with DAG("name")` / `dag_id="name"` | DAG and literal task membership | Parameters assembled at runtime remain unresolved |
| Assigned `DAG(...)` with explicit `dag=variable` | Task membership | Unknown DAG expressions are not guessed |
| Airflow-imported `*Operator` / `*Sensor` with literal `task_id` | Task identity | Arbitrary similarly named classes are not recognized |
| `a >> b`, `b << a`, task/list chains | `NEXT` control edges | Not evidence of data flow or successful execution |
| `set_upstream` / `set_downstream` | `NEXT` control edges | One statically resolved argument |
| Basic `@dag`, `@task`, `@task()` and `.override(task_id="...")` | TaskFlow nodes and direct XCom input dependencies | One top-level call to a parameterless DAG factory; no function execution |
| `ExternalTaskSensor` with literal DAG/task target | `WAITS_FOR` when that target is present | Execution-date alignment and observed success are not proven |

Airflow 2-style imports and Airflow 3's `airflow.sdk` syntax are recognized.
The adapter has synthetic syntax tests and has been exercised on an existing
Airflow repository. It does not claim compatibility with every Airflow/provider
version or reproduce Airflow's scheduler parser.

Loops, conditionals, exception-controlled graph construction, TaskGroups,
dynamic mapping, repeated TaskFlow calls requiring implicit name suffixes, and
parameterized DAG factories are outside the initial supported subset. Detected
boundaries are recorded in `unresolved.jsonl`. Unsupported arbitrary helper
calls can also hide tasks; a small unresolved count is not a completeness score.

## How acceptance works

Extraction produces candidate endpoint pairs with a rule and a pinned source
locator. A separate promotion gate permits only the documented relation rules,
checks endpoint types and DAG ownership, and requires verified evidence records.
The resulting claims are `DECLARED` and `AUTO_VERIFIED` within that static rule
scope. A source hash and line range are retained; source snippets are omitted.

This v1 adapter deliberately concerns control flow. It does not infer SQL table
lineage from Python call names, inspect Spark execution plans, or assert that
an external sensor's runtime conditions are satisfied.

## Reproduce the public check

```sh
palgwae example
palgwae init --source palgwae-example --namespace urn:example:palgwae:airflow
palgwae path urn:example:palgwae:airflow/task/daily_orders/extract \
  urn:example:palgwae:airflow/task/reporting/report --bundle .palgwae/bundle
```

Expected path family: extract → validate or transform → publish → wait_for_orders
→ report. The reverse direction must not be reported as a downstream dependency.

For local validation of your own repository, from a source checkout:

```sh
uv run python scripts/validate_airflow_repository.py /path/to/dags \
  --namespace https://example.org/engineering/pipelines
```

The report contains aggregate counts, evidence-hash checks, dependency-query
checks, and deterministic-rebuild results. It is not a runtime execution test
or a measured precision/recall benchmark. See the [validation report](validation.md).

Airflow's official descriptions of [task dependencies](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)
and [TaskFlow](https://airflow.apache.org/docs/apache-airflow/stable/tutorial/taskflow.html)
explain the underlying declarations.

# Palgwae

**Build shared pipeline context across repositories. Show the evidence. Keep unknowns explicit.**

Palgwae gives developers and coding agents one local graph of declared pipeline
dependencies spread across related repositories. Ask which task starts a job,
which DAG waits on another repository, what a change can affect, and where each
relationship is written in source.

```text
pipeline repo ─┐
airflow repo  ─┼─> palgwae init ─> portable evidence bundle ─> one MCP ─> agents
backend repo  ─┘
```

Extraction is static: Palgwae does not import DAGs, execute repository code,
contact cloud services, or require a model/API key. The development workspace
adapter combines supported Airflow control flow, Terraform AWS declarations,
and literal Python AWS SDK calls. Unsupported or ambiguous relationships stay
explicitly unresolved.

## Quickstart: related repositories

Multi-repository init is available in the current development source and is not
part of the published v0.3.0 wheel. First follow the
[source installation](docs/installation.md#current-source-multi-repository-workspaces),
then run this in the project that will own the generated bundle:

```sh
palgwae init --repo pipeline=. --repo airflow=../airflow --repo backend=../backend \
  --namespace urn:myteam:data-platform --environment prd
palgwae doctor --bundle .palgwae/bundle
palgwae mcp --bundle .palgwae/bundle --transport stdio

# After source changes:
palgwae rebuild
```

Interactive `palgwae init` asks for the same project names and paths. It saves
the selection in `.palgwae/workspace.yaml`, builds one bundle, and prints one
MCP configuration for all registered repositories. See the complete
[workspace guide](docs/workspaces.md) and [agent setup](docs/cross-agent-plugins.md).

Coverage is reported per repository. Registering a backend does not mean its
Java, SQL, dynamic configuration, or runtime behavior was understood.
`doctor: PASS` proves bundle integrity, not graph completeness.

## Stable v0.3.0: Airflow quickstart

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then
install a [release wheel](https://github.com/yonghyeokrhee/Palgwae/releases).
The [installation guide](docs/installation.md) also covers source checkouts,
pnpm, Bun, and npm. PyPI and npm registry publication are separate channels and
are not currently advertised as available.

```sh
palgwae example
palgwae init --source palgwae-example --namespace urn:example:palgwae:airflow
palgwae find publish --bundle .palgwae/bundle
palgwae downstream urn:example:palgwae:airflow/task/daily_orders/publish --bundle .palgwae/bundle
```

The fictional example declares this path:

```text
daily_orders.publish -> reporting.wait_for_orders -> reporting.report
```

Results contain accepted claims and source evidence. `UNKNOWN` means a
relationship was not proven, not that it cannot exist.

For a single Airflow repository:

```sh
palgwae init --source ./dags --namespace https://example.org/engineering/pipelines
```

Use a namespace your organization controls. `init` writes the graph and prints
MCP setup; it does not change your agent settings. Restart MCP after rebuilding
because the process serves an immutable bundle snapshot.

## Connect an agent plugin

The plugin teaches the agent how to query Palgwae and supplies an MCP launch
recipe. It does not install the Python CLI or build a graph; complete the CLI
installation and `init` first.

With the CLI installed and a bundle in your project, in Claude Code:

```text
/plugin marketplace add yonghyeokrhee/Palgwae
/plugin install palgwae@palgwae
```

For Codex:

```sh
codex plugin marketplace add yonghyeokrhee/Palgwae
codex plugin add palgwae@palgwae
```

Try: “Find the publish task. Show the downstream tasks, the evidence for each
edge, and anything unresolved.”

See [agent setup](docs/cross-agent-plugins.md) for PATH/bundle configuration,
OpenCode, and ChatGPT. ChatGPT remote connections and public-directory
submission have additional endpoint and registration requirements; this repo
does not provide a hosted account service.

## What it verifies

The Airflow adapter extracts candidates, then applies explicit rules for literal
DAG/task membership, dependency operators, basic TaskFlow inputs, and resolvable
ExternalTaskSensor targets. Every accepted edge has pinned source provenance.
Dynamic construction is left unresolved where detected.

An existing-repository exercise found 26 DAGs, 99 tasks, 78 within-DAG
dependencies, and seven cross-DAG sensor relationships. Rebuilds matched and
retained source evidence passed hash/locator checks. This was static validation,
not a runtime test or accuracy benchmark. Read [the results and limits](docs/validation.md).

| MCP tool | Use |
| --- | --- |
| `graph_health` | Check bundle integrity and snapshot identity |
| `find_entity` | Resolve a name or canonical ID |
| `get_upstream`, `get_downstream` | Traverse accepted dependencies |
| `find_dependency_path` | Explain a path between two entities |
| `assess_change_impact` | Summarize declared downstream impact |
| `get_claim_evidence` | Retrieve pinned source provenance |

## Why the evidence boundary matters

A call graph, a data catalog, and an orchestrator each capture part of a pipeline.
Palgwae's longer-term model connects eight views: data flow, control flow,
infrastructure, contracts, runtime state, lifecycle, ownership, and evidence.
The name comes from 팔괘, used as a modern metaphor for these views.

The first automatic adapter covers Airflow control flow. The
[original YAML compiler and retail example](examples/retail_pipeline/context-graph.yaml)
demonstrate the broader ontology:

```sh
uv run palgwae build examples/retail_pipeline/context-graph.yaml --output .palgwae/retail
uv run palgwae doctor --bundle .palgwae/retail
uv run palgwae eval --bundle .palgwae/retail --golden examples/retail_pipeline/golden.yaml
```

See [the model](docs/eightfold-context-model.md), [methodology](docs/methodology.md),
[ontology](docs/ontology.md), and [prior art](docs/prior-art.md). Palgwae
complements lineage/catalog tools; it does not replace their runtime collection.

Bundles hold `nodes.jsonl`, `claims.jsonl`, `evidence.jsonl`,
`unresolved.jsonl`, and `manifest.json`. The source checkout's
`web/explorer.html` can inspect these locally without uploads.
[Privacy and trust boundaries](docs/privacy.md) apply when sharing a bundle
with an agent or another person.

## Contribute

Start with a synthetic DAG that illustrates one missing pattern or a case
that must remain unknown. We welcome adapter improvements, negative tests,
and clearer examples. See [CONTRIBUTING.md](CONTRIBUTING.md),
[the roadmap](docs/roadmap.md), and [support](SUPPORT.md).

Optional [Graphify candidate extraction](docs/graphify-integration.md) is isolated
under `integrations/graphify` and is not part of the MCP runtime. Its output
contains zero accepted claims until separately verified.

Apache-2.0. See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md),
[security](SECURITY.md), and [governance](GOVERNANCE.md).

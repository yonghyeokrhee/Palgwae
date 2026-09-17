# Palgwae

<p align="center">
  <img src="assets/branding/palgwae-logo-v4.png" alt="Palgwae — eight trigrams expressing complex relationships through simple forms" width="640">
</p>

**Trace Airflow change impact. Show the evidence. Keep unknowns explicit.**

Palgwae gives developers and coding agents a local graph of declared pipeline
dependencies. Ask what follows a task, which DAG waits on it, and where each
relationship is written in source.

It reads Airflow Python files without importing DAGs or running jobs. Queries
use a portable JSONL snapshot, with no required database, API key, or model call.
Connect the same read-only MCP server to Claude Code, Codex, or another MCP
client.

> Early alpha, 0.3.0. Supports a documented subset of classic Airflow and
> TaskFlow control flow. It does not prove that tasks ran or infer dataset
> lineage from arbitrary Python. [Supported patterns and limits](docs/airflow.md).

### The idea behind the name

We take inspiration from *palgwae* (팔괘/八卦), the eight trigrams, as a way of
reading a complex world through a small vocabulary of simple forms. Solid and
broken lines gain meaning through their combinations and relationships. The
simplicity is in the language, not in the world it describes.

Palgwae brings that intention to software repositories. ELT jobs, Airflow DAGs,
tables, configuration, and cross-repository dependencies are pieces of a
larger system. We make their relationships explicit, evidence-backed, and
readable, so developers and agents can understand the whole without repeatedly
reconstructing it from scattered source files. Simplifying the representation
must not mean hiding uncertainty or inventing missing connections.

The logo follows the same principle: the trigrams themselves carry the idea
of relationships. Their arrangement, repetition, and negative space express
complexity through simple forms; no separate network diagram is needed.

Our eight engineering views are a modern application of this inspiration—not
a one-to-one mapping to the traditional meanings of the trigrams:

1. data flow;
2. control flow;
3. infrastructure;
4. contracts;
5. runtime state;
6. lifecycle;
7. cross-repository ownership;
8. evidence and trust.

Together they expose dependencies that disappear when lineage, orchestration,
deployment, and operational knowledge are inspected separately. See the
[Eightfold Context Model](docs/eightfold-context-model.md).

## Try it

For agent-led setup, copy the [one-go installation prompt](#one-go-setup-prompt-for-an-ai-agent).

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then
install a [release wheel](https://github.com/yonghyeokrhee/Palgwae/releases).
The [installation guide](docs/installation.md) also covers pnpm, Bun, npm,
and source checkouts. PyPI and npm registry publication are separate channels
and are not currently advertised as available.

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

For your repository:

```sh
palgwae init --source ./dags --namespace https://example.org/engineering/pipelines
```

Use a namespace your organization controls. `init` writes the graph and prints
MCP setup; it does not change your agent settings. After source changes, rebuild
the bundle and restart MCP. `doctor` checks snapshot integrity, not live source
freshness.

## Install the plugin

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

### Source-checkout MCP setup

```bash
git clone https://github.com/yonghyeokrhee/Palgwae.git
cd Palgwae
uv sync --frozen
```

Generic MCP client configuration:

```json
{
  "mcpServers": {
    "palgwae": {
      "command": "uv",
      "args": [
        "run",
        "--frozen",
        "--project",
        "/absolute/path/to/Palgwae",
        "palgwae",
        "mcp",
        "--bundle",
        "/absolute/path/to/bundle",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

Palgwae also ships thin distributions for
[Codex, Claude Code, and OpenCode](docs/cross-agent-plugins.md). They all start
the same stdio MCP server and apply the same evidence-bounded query contract;
the client-specific files contain installation metadata and workflow guidance,
not graph semantics.

The Codex plugin is plug-and-play from a source marketplace: it includes its
own Palgwae Python runtime, so a separate global `palgwae` installation is not
required. On first use it initializes `.palgwae/bundle` in the owner project.
A conventional `palgwae-context-graph.yaml` (or `.yml`/`.json`) is compiled
automatically. If no spec exists, Palgwae creates a valid fail-closed starter
with one repository node, zero accepted claims, and an explicit unresolved
boundary. The starter makes MCP available immediately without pretending that
repository relationships were extracted.

## Install in your project

The **owner project** is the repository whose pipelines you want to query;
it is separate from the Palgwae checkout. The commands below use the source
checkout above, not a package assumed to exist on PyPI. For
reproducible installations, check out a reviewed Palgwae commit and keep its
`uv.lock` unchanged.

```bash
# Replace these with absolute paths. No global palgwae command is needed.
PALGWAE_DIR="/absolute/path/to/Palgwae"
OWNER_DIR="/absolute/path/to/your-project"

uv sync --frozen --project "$PALGWAE_DIR"
uv run --frozen --project "$PALGWAE_DIR" palgwae bootstrap \
  --project-root "$OWNER_DIR" --output .palgwae/bundle
uv run --frozen --project "$PALGWAE_DIR" palgwae doctor \
  --bundle "$OWNER_DIR/.palgwae/bundle"
```

Bootstrap reuses a valid existing bundle, compiles a conventional project spec
when the bundle is missing, or creates the empty starter described above.
**It does not automatically extract pipeline relationships from arbitrary
source code.** Use the agent prompt below to prepare that evidence-backed
context, or write an [adapter](docs/writing-an-adapter.md).

To connect, use the generic MCP configuration above with your absolute
Palgwae path and `OWNER_DIR/.palgwae/bundle` as the bundle path. These are literal
paths in JSON, not shell variables. Use your client's native configuration
format; merge the Palgwae entry without replacing other servers. If the client
cannot find `uv`, set `command` to its absolute executable path. Alternatively,
follow the [client-specific plugin installation](docs/cross-agent-plugins.md).
Restart or reconnect MCP after changing the bundle: the server loads its
snapshot at startup.

### One-go setup prompt for an AI agent

Open the **owner project** in your coding agent and paste the following prompt.
It authorizes local setup and verification, not production execution or
publishing. The agent needs shell/file access and permission to update the
chosen MCP configuration. A client that cannot reload tools during a session
may still require a reconnect or a new session.

```text
Install and connect Palgwae to this owner project, then prove that its MCP
tools can answer a real pipeline question. Execute the work, not just a plan.

1. Resolve the current workspace's owner-project root. Inspect its instructions,
   Git status, and existing Palgwae/MCP configuration. Preserve unrelated edits,
   existing curated graphs, and other MCP servers. Do not run ETL jobs, access
   production services, read secrets, upload source, commit, or push.

2. Reuse an existing Palgwae checkout, or clone
   https://github.com/yonghyeokrhee/Palgwae.git into a separate tools directory
   outside the owner repository. Read its README, docs/methodology.md,
   docs/ontology.md, docs/writing-an-adapter.md, and the retail example spec and
   Golden tests. Record the Palgwae revision and any local modifications. Use
   the requested revision if one was supplied; do not reset an existing checkout.

3. Check Python 3.11+ and uv. If missing, install them using the platform's
   supported official instructions and the environment's approval policy.
   Resolve absolute PALGWAE_DIR and OWNER_DIR paths, then run:
     uv sync --frozen --project "$PALGWAE_DIR"
     uv run --frozen --project "$PALGWAE_DIR" palgwae bootstrap --help
     uv run --frozen --project "$PALGWAE_DIR" palgwae bootstrap \
       --project-root "$OWNER_DIR" --output .palgwae/bundle
   If this revision lacks bootstrap, report the version mismatch instead of
   inventing a command. A starter with zero accepted claims is not completion.

4. Reuse a suitable existing spec, or inspect the owner's source, SQL, schedules,
   and configuration to model one representative end-to-end pipeline. Create
   palgwae-context-graph.yaml at the owner root without overwriting existing
   work. Set SPEC_PATH to the absolute path of the reused or new spec.
   Use organization-controlled canonical URIs, never fictional example
   IDs; ask only if the namespace or an essential identity is ambiguous.
   Resolve ontology and evidence paths relative to the spec. Pin the actual
   source revision and exact line ranges; disclose dirty-source provenance.
   Follow the acceptance rubric: a valid locator alone does not prove a
   relationship. Do not mark model guesses as AUTO_VERIFIED or invent human
   approval. Keep dynamic targets and unsupported relationships unresolved.

5. Build into a new, unused owner-local bundle directory so existing snapshots
   remain intact. Resolve its absolute path as BUNDLE_DIR, then run:
     uv run --frozen --project "$PALGWAE_DIR" palgwae build \
       "$SPEC_PATH" --output "$BUNDLE_DIR"
     uv run --frozen --project "$PALGWAE_DIR" palgwae doctor --bundle "$BUNDLE_DIR"
   Create owner-specific Golden tests for entity resolution, a source-supported
   path, and an unproven query that must return UNKNOWN. Run palgwae eval with
   --bundle "$BUNDLE_DIR" and --golden pointing to those tests. Do not copy the
   fictional example's expected answers. Bootstrap does not refresh an existing
   bundle; use an explicit build when the spec changes.

6. Detect the current MCP client and merge a project-scoped Palgwae server entry
   using its supported configuration format. Launch the absolute uv executable
   with arguments:
     run --frozen --project <absolute PALGWAE_DIR> palgwae mcp
     --bundle <absolute BUNDLE_DIR> --transport stdio
   Substitute actual paths, not placeholders or shell variables. Preserve other
   settings and avoid duplicate Palgwae servers. Prefer project scope; ask before
   changing shared user-wide configuration if project scope is unavailable.

7. Reconnect and test through MCP, not CLI queries alone: initialize, list the
   seven documented tools, call graph_health, resolve a real entity with
   find_entity, traverse a supported path, and call get_claim_evidence for a
   returned claim. Check that MCP reports the validated bundle's snapshot.
   If this session cannot reload its tools, test the configured command through
   an MCP SDK stdio client and separately state that host-client activation is
   pending. Do not claim live integration based only on a config file or doctor.

8. Answer one real owner-project lineage or change-impact question using MCP
   evidence, with source locators and unresolved boundaries. Finish with the
   changed paths, revisions, snapshot ID, node/accepted-claim/unresolved counts,
   doctor and Golden results, actual MCP calls tested, and any exact reconnect
   action still needed. Distinguish installation, populated context, protocol
   verification, and host-client activation. If evidence or permissions block
   a step, report the partial result honestly and the smallest next action.
```

## Performance comparison

An early matched-model pilot compared two ways for an AI coding agent to answer
the same multi-part lineage and change-impact question in a real-world AWS Glue
ETL repository:

1. **Search only:** inspect a clean, tracked-only checkout with ordinary source
   search and file reads.
2. **Palgwae MCP:** query a prebuilt accepted graph, then retrieve the pinned
   evidence for material relationships.

Both runs used `gpt-5.6-terra` with medium reasoning and ran sequentially. The
task required the agent to trace a raw report through its producer, every
producer output, a downstream consumer and its schedule, and the final MySQL
dataset; cite file and line evidence; identify unresolved boundaries; and
assess an intermediate schema change.

| Metric | Search only | Palgwae MCP | Difference |
|---|---:|---:|---:|
| Wall time | 91.24 s | 65.87 s | **27.8% faster** |
| Input tokens | 319,849 | 253,996 | **20.6% fewer** |
| Output tokens | 3,842 | 2,633 | **31.5% fewer** |
| Shell commands | 7 | 3 | **57.1% fewer** |

Both runs recovered the core four-hop data path, all four producer outputs,
the consumer schedule, and source locators. The MCP result additionally bound
the answer to a validated snapshot and returned explicit evidence and
unresolved records. The search-only result found producer-control details that
were outside the pilot graph and provided deeper field-level schema analysis.

The practical result is intentionally narrower than “MCP beats search”:

- Palgwae improved latency, context usage, and reproducibility for relationships
  already represented in the accepted graph.
- Source search remained necessary for facts outside the bundle and for semantic
  code analysis below the modeled relationship level.
- Graph extraction, review, and bundle-build time were not included. The
  comparison measures query-time agent performance after the Palgwae context
  has been prepared.
- This was one representative task with one run per arm, not a statistical
  benchmark. Treat the numbers as an initial case study and reproduce the
  comparison on your own repositories and questions.


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

## Author

Created by Yonghyeok Rhee.

[LinkedIn](https://www.linkedin.com/in/yong) ·
[Blog](https://yonghyeokrhee.github.io/)

## License

Apache-2.0. See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md),
[security](SECURITY.md), and [governance](GOVERNANCE.md).

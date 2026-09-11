# One workspace, related repositories, one context graph

This feature is available in the development source, not the published 0.3.0
wheel. Follow the
[current-source installation](installation.md#current-source-multi-repository-workspaces),
or run the checkout with `uv run --project /path/to/Palgwae palgwae ...`.

```text
registered source checkouts
        │ static extraction
        ▼
.palgwae/workspace.yaml ──> .palgwae/bundle ──> one read-only MCP server
                                                        │
                                      Codex / Claude / OpenCode / other clients
```

Prerequisites:

- Python 3.11+ and a Palgwae source installation;
- every related repository already checked out locally;
- one directory chosen as the workspace owner;
- one namespace controlled by the user or organization.

## Initialize

Run `palgwae init` in the project that will own the generated knowledge. The
owner is only the location of `.palgwae/`; it receives no special graph meaning.
In an interactive terminal it asks for related project names or `NAME=PATH`
entries, then an organization-controlled namespace URI. A simple name is resolved in
the current directory and its parent; ambiguous names require an explicit
path. Repositories must already be checked out. Initialization does not clone
private repositories or run their code.

For scripts, provide the same choices as flags:

```sh
cd pipeline
palgwae init \
  --repo pipeline=. \
  --repo airflow=../airflow \
  --repo backend=../backend \
  --namespace urn:myteam:data-platform \
  --environment prd
```

The list is explicit: include `.` when the current project should participate.
Only a blank interactive selection defaults to the current project. This
produces:

```text
pipeline/.palgwae/
  workspace.yaml   # names, relative checkout paths, namespace, environment
  bundle/          # one portable graph for every registered project
```

Example saved configuration:

```yaml
version: 1
namespace: urn:myteam:data-platform
environment: prd
projects:
  - name: airflow
    path: ../airflow
  - name: backend
    path: ../backend
  - name: pipeline
    path: .
```

Paths are relative to the owner checkout, one level above `.palgwae/`. Keep
project names and namespace stable: node identities include both, so two
projects can have similarly named tasks without being collapsed together.
Share `workspace.yaml` when team checkout layout is consistent, or keep it
local. `.palgwae/` is ignored by default, so sharing requires an explicit review
and force-add; project names and topology may be confidential even though paths
are relative. No local absolute path is put into the portable graph manifest.

`--environment` selects a supported source configuration such as `prd.tfvars`.
It is a label and extraction scope, not a cloud connection: init makes no AWS
or Airflow API calls.

## What the combined graph proves

Palgwae stages supported tracked source files from each Git checkout, or source
files from a non-Git directory. Working-tree bytes are used, not an implicit
branch fetch. Content fingerprints accompany the Git HEAD in coverage, so
uncommitted tracked edits are not mislabeled as committed content. Untracked
Git files are excluded; add new source files to Git before rebuilding.

Native adapters cover these patterns:

- The documented Airflow subset, including an ExternalTaskSensor whose
  literal DAG/task target resolves uniquely in another registered repository.
- Literal Terraform resource names, and `for_each = var.some.map` with
  `name = each.key` (or `function_name = each.key`) resolved from a unique
  selected variable source. `terraform.tfvars` and matching environment files
  in conventional module configuration directories are supported. Unhandled
  automatic variable overrides, Terraform override files, count expressions,
  modules and provider aliases are unresolved; Terraform itself is not executed.
- Exact imported GlueJobOperator/LambdaInvokeFunctionOperator target names
  matched to a unique Terraform resource declaration.
- A bounded Python boto3 client call with a literal Glue JobName or Lambda
  FunctionName, matched to a unique resource declaration. Arbitrary receivers,
  dynamic targets, qualified ARNs and explicit connection overrides remain
  unresolved.

The workspace declares a shared logical deployment scope. Only register
projects meant to operate together, with one selected environment. A unique
bare AWS name in that scope is a declared source binding; it does not prove
that an AWS resource exists or a call ran. Explicit operator regions,
nondefault/dynamic connections (including unresolved DAG or task `default_args`),
provider aliases and SDK connection overrides need scope-aware resolution and
are currently unresolved. Separately deployed
Airflow installations should use separate workspaces until deployment scope
is modeled explicitly. Local sensor targets take precedence; multiple external
matches are never resolved by picking the first one.

Cross-repo resource claims contain evidence for both the invocation and the
target declaration. A missing or ambiguous target is visible in unresolved
records. Graphify remains an optional, separate candidate extractor; init does
not execute Graphify or make model calls.

Registering a Java backend, SQL repository, or complex Glue script provides
inventory and a coverage boundary, not a claim that all its relationships were
extracted. Coverage is always partial in this version. Full SQL/Spark lineage,
MyBatis service bindings, marker contracts, historical decisions, runtime
activity, and all account/region/provider variants require further adapters
or supplied evidence. `doctor: PASS` means bundle integrity, not full coverage.

## Use the graph from an agent

Init prints a single `mcp_config`. Its command points to the Python installation
used for init and its arguments point to the owner bundle. Copy that recipe
into any stdio MCP host; no per-repository servers are required. If `palgwae`
is already the intended version on PATH, this equivalent command also works:

```sh
palgwae mcp --bundle .palgwae/bundle --transport stdio
# Optional shared localhost process:
palgwae mcp --bundle .palgwae/bundle --transport http --host 127.0.0.1 --port 8765
```

The seven existing tools are unchanged. `graph_health` additionally exposes
`sources` and `build.coverage`, including each repository's identity, source
fingerprint, supported extraction counts and unsupported extensions. Ask the
agent to resolve entities first, follow accepted paths, and inspect evidence
from both sides of a cross-project relationship. Fuzzy matches are candidate
names, not proof that a requested table or contract exists.

The portable bundle also works through the core API and CLI; MCP is one way
to make it available as agent context. Serving it requires neither access to
the source checkouts nor Terraform, Airflow, cloud credentials or models.

The generated `mcp_config` is machine-specific because it pins the Python
executable and absolute bundle path used during init. Put it in local client
settings; do not commit that recipe. For a team, distribute Palgwae and the
reviewed bundle separately, then give each developer a local bundle path.

## Refresh and recovery

Edit the saved project list to add/remove repositories, then run:

```sh
palgwae rebuild
# Or, from another directory:
palgwae rebuild --workspace /path/to/pipeline/.palgwae/workspace.yaml
```

Rebuild stages and validates the next graph before publishing it. Missing
repositories and failed extraction preserve the previous bundle. A per-output
lock prevents simultaneous publication; a stale lock is an actionable error.
Older workspace bundles are retained as `.bundle.previous-*` directories next
to the active bundle for recovery; retention cleanup is manual in this version.
Unrelated bundles are never replaced. Restart the MCP process after rebuilding:
the server loads an immutable snapshot at startup. No host settings are changed
by init or rebuild.

The legacy `palgwae init --source ./dags --namespace ...` command remains
Airflow-only and does not create a repository workspace.

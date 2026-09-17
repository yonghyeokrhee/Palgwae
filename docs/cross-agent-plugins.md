# Cross-agent distribution

Palgwae has one product-neutral runtime and three thin client distributions.
The MCP tool schemas and accepted graph bundle are the compatibility boundary;
client plugin formats are not.

```text
accepted bundle -> Palgwae MCP -> Codex
                              -> Claude Code
                              -> OpenCode
```

## Shared prerequisites

Claude Code and OpenCode currently require the `palgwae` executable on `PATH`.
They also require an accepted bundle at `.palgwae/bundle`:

```bash
palgwae build path/to/context-graph.yaml --output .palgwae/bundle
palgwae doctor --bundle .palgwae/bundle
```

Projects may use another bundle location by copying the relevant client
configuration and changing only the `--bundle` argument. Do not commit
machine-specific absolute paths.

## Codex

The Codex distribution lives under `plugins/palgwae`. It bundles the Python
runtime, a launcher, the MCP server declaration, and a `trace-pipeline` skill.
Only `uv` is required on the host; a global `palgwae` installation is not.
Validate the plugin with the OpenAI plugin validator before publishing it to a
marketplace.

Codex starts the launcher from the installed plugin root. The launcher restores
the inherited owner repository (with parent-process lookup as a fallback)
before resolving the project-relative bundle. `PALGWAE_PROJECT_ROOT` is an
explicit override for hosts that do not preserve the owner directory or expose
their parent working directory. Codex CLI `--cd`/`-C` is resolved from the
parent argv; `/proc` and `lsof` cover ordinary current-directory launches.

For source-checkout testing, add this repository as a Codex marketplace and
install the plugin:

```bash
codex plugin marketplace add /path/to/Palgwae
codex plugin add palgwae@palgwae
```

The marketplace entry is `.agents/plugins/marketplace.json`. Installation does
not bypass the user's MCP or tool-approval policy.

On the first MCP start, the launcher initializes `.palgwae/bundle` in the
current owner repository:

- a root `palgwae-context-graph.yaml`, `.yml`, or `.json` is compiled when
  present (`.palgwae/context-graph.yaml`, `.yml`, or `.json` is also discovered);
- otherwise a fail-closed starter is written with one repository node, no
  accepted claims, and one unresolved extraction boundary;
- an existing bundle is hash-validated and never silently replaced;
- concurrent first starts are serialized by a project-local bootstrap lock;
- a partial or non-empty bundle directory is preserved and startup fails with
  an actionable error.

The bootstrap write is why the plugin declares both Read and Write capability,
even though all seven MCP tools remain read-only. To initialize explicitly
outside Codex, run:

```bash
palgwae bootstrap --project-root . --output .palgwae/bundle
```

## Claude Code

The Claude Code distribution lives under `plugins/claude/palgwae`. During
development it can be loaded with:

```bash
claude --plugin-dir ./plugins/claude/palgwae
```

## OpenCode

`clients/opencode/opencode.json` is the smallest supported integration. Merge
its `mcp` and `permission` entries into an existing OpenCode config. A native
OpenCode plugin should be added only when Palgwae needs OpenCode lifecycle
hooks; graph retrieval does not require them.

## Shared behavioral contract

Every client must discover the same seven read-only tools and return identical
structured results for the same bundle. Client-specific instructions may teach
the query workflow but must not change graph semantics:

1. resolve with `find_entity`;
2. traverse accepted claims;
3. inspect claim evidence;
4. preserve `UNKNOWN` as an unproven boundary;
5. never treat extractor candidates as accepted knowledge.

# Cross-agent distribution

Palgwae has one product-neutral runtime and three thin client distributions.
The MCP tool schemas and accepted graph bundle are the compatibility boundary;
client plugin formats are not.

```text
accepted bundle -> Palgwae MCP -> Codex
                              -> Claude Code
                              -> OpenCode
```

## Prerequisites

The current project must make the `palgwae` executable available on `PATH` and
build its accepted bundle at `.palgwae/bundle`:

```bash
palgwae build path/to/context-graph.yaml --output .palgwae/bundle
palgwae doctor --bundle .palgwae/bundle
```

Projects may use another bundle location by copying the relevant client
configuration and changing only the `--bundle` argument. Do not commit
machine-specific absolute paths.

## Codex

The Codex distribution lives under `plugins/palgwae`. It bundles a
read-only MCP server declaration and a `trace-pipeline` skill. Validate it with
the OpenAI plugin validator before publishing it to a marketplace.

For source-checkout testing, add this repository as a Codex marketplace and
install the plugin:

```bash
codex plugin marketplace add /path/to/Palgwae
codex plugin add palgwae@palgwae
```

The marketplace entry is `.agents/plugins/marketplace.json`. Installation does
not bypass the user's MCP or tool-approval policy.

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

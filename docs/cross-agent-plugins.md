# Connect your coding agent

Claude Code and OpenCode require the [CLI](installation.md) on PATH and a
bundle created by `palgwae init` or `palgwae build`. The default bundle is
`.palgwae/bundle`; restart desktop hosts after installing the CLI. The Codex
plugin bundles its own runtime and can bootstrap a missing bundle.

## Claude Code

```text
/plugin marketplace add yonghyeokrhee/Palgwae
/plugin install palgwae@palgwae
```

Enable it from the repository containing the bundle. Try: “Find the publish
task, trace its downstream dependencies, and show the source evidence and
unresolved boundaries.”

The catalog is `.claude-plugin/marketplace.json`. For checkout testing, run
`claude --plugin-dir ./plugins/claude/palgwae`. A listing in the official Claude
directory requires a separate submission. See
[Claude's marketplace guide](https://code.claude.com/docs/en/plugin-marketplaces).

## Codex and local ChatGPT desktop authoring

```sh
codex plugin marketplace add yonghyeokrhee/Palgwae
codex plugin add palgwae@palgwae
```

The repo catalog at `.agents/plugins/marketplace.json` exposes
`plugins/palgwae`. Enable it in a new task with your project as the working
directory. OpenAI describes a common `.codex-plugin/plugin.json` package and
repo/personal sources in the desktop Plugins Directory. Local-source
availability varies by surface. See
[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).

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


A starter is not extracted pipeline context. Use `palgwae init` for supported
Airflow sources, or build an evidence-backed project spec, then restart MCP.
For an alternate bundle location, update the local MCP configuration without
publishing machine-specific paths in the plugin distribution.

## ChatGPT remote MCP and public directory

ChatGPT developer mode supports public HTTPS or Secure MCP Tunnel. A tunnel can
reach stdio or local HTTP for private testing; public submission requires a
public HTTPS endpoint. Account/workspace policy controls developer-mode
availability. See [OpenAI's connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).

Palgwae ships the server but no hosted service, OAuth account system, or
pre-registered ChatGPT connection. For local HTTP:

```sh
palgwae mcp --bundle .palgwae/bundle --transport http --host 127.0.0.1 --port 8765
```

MCP is at `/mcp/`; health is at `/api/health`. Use a fictional bundle for a
public test. Private bundles need an appropriately authenticated deployment,
not an unauthenticated forwarding service. After registering a real connection,
its actual `plugin_asdk_app...` ID can be wired through an `.app.json`
companion. No connection ID is fabricated in this package.

OpenAI's public directory serves ChatGPT and Codex. Publication there is a
reviewed submission, distinct from distributing this GitHub catalog. This
release provides local plugins and a server for connection testing; it does
not claim a public-directory listing.

## OpenCode and generic MCP

Merge the relevant entries from `clients/opencode/opencode.json`. Generic
stdio configuration is also printed by `palgwae init`:

```json
{
  "mcpServers": {
    "palgwae": {
      "command": "palgwae",
      "args": ["mcp", "--bundle", ".palgwae/bundle", "--transport", "stdio"]
    }
  }
}
```

Resolve with `find_entity` before traversal. Inspect `get_claim_evidence` and
preserve `UNKNOWN` as unproven. Control-flow evidence does not prove dataset
lineage or a successful run.

If tools do not appear, run the configured command in the project's terminal.
Check executable PATH, bundle path, and working directory. Rebuild after source
changes and restart MCP. Subprocess parity tests exercise the configurations,
but do not substitute for each host's interactive installation or review.

# Connect your coding agent

Install the [CLI](installation.md), then run `palgwae init` in your repository.
The default bundle is `.palgwae/bundle`. The executable must be on the host's
PATH; restart desktop hosts after installing it.

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

The configuration starts `palgwae mcp --bundle .palgwae/bundle`. If a host uses
another working directory, put the absolute bundle path printed by `init`
in your local MCP configuration. Never publish your machine-specific path in
the plugin distribution.

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

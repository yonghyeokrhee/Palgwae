# Palgwae for Claude Code

Prerequisites:

1. Install the `palgwae` command.
2. Build the current project's accepted bundle at `.palgwae/bundle`.
3. Test this directory with `claude --plugin-dir ./plugins/claude/palgwae`.

Claude Code will ask the user to approve a project/plugin-provided MCP server.
The server is read-only and starts as a local stdio process.

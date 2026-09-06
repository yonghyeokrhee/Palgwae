# Palgwae for OpenCode

Install the `palgwae` command and build an accepted graph at
`.palgwae/bundle`. Merge `opencode.json` into the project's configuration or
copy it as the initial project config.

This uses OpenCode's MCP client directly. A native JavaScript plugin is not
required because Palgwae does not need to intercept model requests or tool
execution. The same read-only MCP contract is used by Codex and Claude Code.

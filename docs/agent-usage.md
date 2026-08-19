# Palgwae agent usage policy

Palgwae's MCP server is designed to provide shared context, not autonomous
truth.

Recommended agent sequence:

1. Call `graph_health` and retain the snapshot ID.
2. Resolve a human name with `find_entity`.
3. Traverse only from the returned canonical ID.
4. For material dependencies, fetch claim evidence.
5. Treat `UNKNOWN` as an evidence gap.
6. Fall back to current source or runtime metadata to close that gap.
7. Report the snapshot ID and unresolved boundaries in high-risk answers.

An agent should never:

- claim completeness from an empty traversal;
- use a runtime observation as proof of authoritative ownership;
- hide environment or repository scope;
- mutate accepted graph files through query tools;
- infer retirement because a resource was quiet for a short window.

The same policy works with Codex, Claude, VS Code, Cursor, or any other
MCP-compatible client because it describes tool behavior rather than a
vendor-specific prompt.

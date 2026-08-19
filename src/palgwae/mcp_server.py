"""Optional Model Context Protocol adapter for the read-only graph."""

from __future__ import annotations

from contextlib import asynccontextmanager
import ipaddress
from pathlib import Path
from typing import Any

from .bundle import GraphBundle
from .graph import ContextGraph


MCP_INSTRUCTIONS = (
    "Palgwae is a read-only, evidence-bounded data-engineering context graph. "
    "Resolve names "
    "with find_entity before traversal. Treat UNKNOWN as an unproven "
    "relationship, not proof of absence. Inspect claim evidence before "
    "presenting a material dependency as confirmed."
)


def _mcp_imports() -> tuple[Any, Any]:
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise RuntimeError(
            "MCP support is not installed; install the project MCP extra"
        ) from exc
    return FastMCP, ToolAnnotations


def create_mcp(bundle_path: str | Path) -> Any:
    """Create a FastMCP server without importing MCP in the core runtime."""

    FastMCP, ToolAnnotations = _mcp_imports()
    graph = ContextGraph(GraphBundle.load(bundle_path))
    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    mcp = FastMCP(
        "palgwae",
        instructions=MCP_INSTRUCTIONS,
        streamable_http_path="/",
        json_response=True,
    )

    @mcp.tool(annotations=read_only, structured_output=True)
    def graph_health() -> dict[str, Any]:
        """Validate hashes and report the active snapshot identity."""

        return graph.health()

    @mcp.tool(annotations=read_only, structured_output=True)
    def find_entity(
        query: str, node_type: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Resolve a name, ID, type, or alias to canonical graph entities."""

        return graph.find(query, node_type=node_type, limit=limit)

    @mcp.tool(annotations=read_only, structured_output=True)
    def get_upstream(node_id: str, max_hops: int = 6) -> dict[str, Any]:
        """Return accepted evidence-backed upstream dependency paths."""

        return graph.upstream(node_id, max_hops=max_hops)

    @mcp.tool(annotations=read_only, structured_output=True)
    def get_downstream(node_id: str, max_hops: int = 6) -> dict[str, Any]:
        """Return accepted evidence-backed downstream dependency paths."""

        return graph.downstream(node_id, max_hops=max_hops)

    @mcp.tool(annotations=read_only, structured_output=True)
    def find_dependency_path(
        source_node_id: str,
        target_node_id: str,
        max_hops: int = 8,
    ) -> dict[str, Any]:
        """Find shortest accepted dependency-flow paths between two entities."""

        return graph.path(
            source_node_id, target_node_id, max_hops=max_hops
        )

    @mcp.tool(annotations=read_only, structured_output=True)
    def assess_change_impact(
        node_id: str,
        change_type: str = "unspecified",
        max_hops: int = 6,
    ) -> dict[str, Any]:
        """Summarize the evidence-backed downstream blast radius."""

        return graph.impact(
            node_id, change_type=change_type, max_hops=max_hops
        )

    @mcp.tool(annotations=read_only, structured_output=True)
    def get_claim_evidence(claim_id: str) -> dict[str, Any]:
        """Return pinned source locators and hashes for a graph claim."""

        return graph.claim_evidence(claim_id)

    # Useful to embedders and tests without making it part of the MCP schema.
    mcp._palgwae_graph = graph
    return mcp


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_http_app(bundle_path: str | Path) -> Any:
    """Create a loopback-hostable Starlette app with MCP at ``/mcp``."""

    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse, RedirectResponse
        from starlette.routing import Mount, Route
    except ImportError as exc:
        raise RuntimeError(
            "HTTP MCP support requires the project's MCP dependencies"
        ) from exc

    mcp = create_mcp(bundle_path)
    graph: ContextGraph = mcp._palgwae_graph

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            graph.health(), headers={"Cache-Control": "no-store"}
        )

    async def root(_: Request) -> RedirectResponse:
        return RedirectResponse("/api/health")

    @asynccontextmanager
    async def lifespan(_: Any):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Mount("/mcp", app=mcp.streamable_http_app()),
            Route("/api/health", health),
            Route("/", root),
        ],
        lifespan=lifespan,
    )
    app.state.context_graph = graph
    app.state.mcp = mcp
    return app


def run_mcp(
    bundle_path: str | Path,
    *,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Run stdio MCP or a Streamable HTTP endpoint on loopback."""

    if transport == "stdio":
        create_mcp(bundle_path).run(transport="stdio")
        return
    if transport != "http":
        raise ValueError("transport must be 'stdio' or 'http'")
    if not _is_loopback(host):
        raise ValueError(
            "HTTP transport is loopback-only; use 127.0.0.1, ::1, or localhost"
        )
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("HTTP MCP support requires uvicorn") from exc
    uvicorn.run(
        create_http_app(bundle_path),
        host=host,
        port=port,
        log_level="info",
    )

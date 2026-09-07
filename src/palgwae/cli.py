"""Command-line interface for building, querying, and serving graph bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from importlib.metadata import version
from typing import Any, Sequence

from .builder import build_bundle
from .bundle import BundleValidationError, GraphBundle, doctor_bundle
from .demo import create_demo_bundle
from .graph import ContextGraph


def _bundle_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="directory containing manifest.json and the graph JSONL files",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="palgwae",
        description=(
            "Build and query an evidence-bounded dependency graph for a "
            "data-engineering project."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"palgwae {version('palgwae')}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    airflow = commands.add_parser("airflow", help="extract declared Airflow control flow without executing DAGs")
    airflow.add_argument("source", type=Path, help="directory of Airflow Python sources")
    airflow.add_argument("--namespace", required=True, help="organization-controlled URI for graph identities")
    airflow.add_argument("--output", type=Path, default=Path(".palgwae/bundle"))

    init = commands.add_parser("init", help="build an Airflow bundle and print local MCP setup")
    init.add_argument("--source", type=Path, default=Path("dags"))
    init.add_argument("--namespace", required=True)
    init.add_argument("--output", type=Path, default=Path(".palgwae/bundle"))

    sample = commands.add_parser("example", help="write a fictional Airflow source file for a first run")
    sample.add_argument("--output", type=Path, default=Path("palgwae-example"))

    demo = commands.add_parser("demo", help="write a self-contained demo bundle")
    demo.add_argument(
        "--output",
        type=Path,
        default=Path("palgwae-demo"),
        help="new directory for the demo (default: ./palgwae-demo)",
    )

    build = commands.add_parser(
        "build", help="compile a YAML or JSON project spec into a graph bundle"
    )
    build.add_argument("spec", type=Path)
    build.add_argument("--output", type=Path, required=True)

    doctor = commands.add_parser("doctor", help="validate bundle hashes and records")
    _bundle_argument(doctor)

    find = commands.add_parser("find", help="resolve an entity name or alias")
    find.add_argument("query")
    _bundle_argument(find)
    find.add_argument("--node-type")
    find.add_argument("--limit", type=int, default=10)

    upstream = commands.add_parser(
        "upstream", help="show proven upstream dependency paths"
    )
    upstream.add_argument("node_id")
    _bundle_argument(upstream)
    upstream.add_argument("--max-hops", type=int, default=6)

    downstream = commands.add_parser(
        "downstream", help="show proven downstream dependency paths"
    )
    downstream.add_argument("node_id")
    _bundle_argument(downstream)
    downstream.add_argument("--max-hops", type=int, default=6)

    path = commands.add_parser(
        "path", help="find a proven dependency path between two nodes"
    )
    path.add_argument("source_node_id")
    path.add_argument("target_node_id")
    _bundle_argument(path)
    path.add_argument("--max-hops", type=int, default=8)

    impact = commands.add_parser(
        "impact", help="assess the proven downstream blast radius"
    )
    impact.add_argument("node_id")
    _bundle_argument(impact)
    impact.add_argument("--change-type", default="unspecified")
    impact.add_argument("--max-hops", type=int, default=6)

    mcp = commands.add_parser(
        "mcp", help="serve the graph through Model Context Protocol"
    )
    _bundle_argument(mcp)
    mcp.add_argument(
        "--transport", choices=("stdio", "http"), default="stdio"
    )
    mcp.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host; loopback addresses only (default: 127.0.0.1)",
    )
    mcp.add_argument("--port", type=int, default=8765)

    evaluate = commands.add_parser(
        "eval", help="run structured Golden questions against a bundle"
    )
    _bundle_argument(evaluate)
    evaluate.add_argument("--golden", type=Path, required=True)

    # Earlier prototypes used this spelling.  Keeping it as a quiet alias makes
    # local experiments reproducible while the public documentation stays on
    # the shorter `demo` command.
    init_demo = commands.add_parser(
        "init-demo", help=argparse.SUPPRESS
    )
    init_demo.add_argument("--output", type=Path, default=Path("palgwae-demo"))
    return parser


def _print_json(value: Any) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "example":
            from importlib.resources import files

            args.output.mkdir(parents=True, exist_ok=True)
            target = args.output / "pipeline.py"
            with target.open("x", encoding="utf-8") as handle:
                handle.write(files("palgwae").joinpath("resources/airflow_example.py").read_text())
            _print_json({"created": str(target), "next": f"palgwae init --source {args.output} --namespace urn:example:palgwae:airflow"})
            return 0

        if args.command in {"airflow", "init"}:
            from .airflow import build_airflow

            report = build_airflow(args.source, args.output, args.namespace)
            if args.command == "init":
                report["mcp_config"] = {"mcpServers": {"palgwae": {
                    "command": "palgwae", "args": ["mcp", "--bundle", str(args.output.resolve()), "--transport", "stdio"]}}}
                report["next"] = "Install the Palgwae plugin in your project, or copy mcp_config into your client's MCP settings."
            _print_json(report)
            return 0

        if args.command in {"demo", "init-demo"}:
            bundle = create_demo_bundle(args.output)
            result = bundle.doctor()
            result["created"] = str(bundle.bundle_dir)
            _print_json(result)
            return 0

        if args.command == "build":
            bundle = build_bundle(args.spec, args.output)
            result = bundle.doctor()
            result["created"] = str(bundle.bundle_dir)
            build_metadata = bundle.manifest.get("build") or {}
            result["source_spec"] = str(
                build_metadata.get("spec") or args.spec.name
            )
            _print_json(result)
            return 0

        if args.command == "doctor":
            result = doctor_bundle(args.bundle)
            _print_json(result)
            return 0 if result["status"] == "PASS" else 2

        if args.command == "mcp":
            # Import lazily so build/query usage does not require MCP.
            from .mcp_server import run_mcp

            run_mcp(
                args.bundle,
                transport=args.transport,
                host=args.host,
                port=args.port,
            )
            return 0

        if args.command == "eval":
            from .evaluation import evaluate_golden

            result = evaluate_golden(args.bundle, args.golden)
            _print_json(result)
            return 0 if result["status"] == "PASS" else 1

        graph = ContextGraph(GraphBundle.load(args.bundle))
        if args.command == "find":
            result = graph.find(
                args.query, node_type=args.node_type, limit=args.limit
            )
        elif args.command == "upstream":
            result = graph.upstream(args.node_id, max_hops=args.max_hops)
        elif args.command == "downstream":
            result = graph.downstream(args.node_id, max_hops=args.max_hops)
        elif args.command == "path":
            result = graph.path(
                args.source_node_id,
                args.target_node_id,
                max_hops=args.max_hops,
            )
        elif args.command == "impact":
            result = graph.impact(
                args.node_id,
                change_type=args.change_type,
                max_hops=args.max_hops,
            )
        else:  # pragma: no cover - argparse enforces the command set.
            raise ValueError(f"unsupported command: {args.command}")
        _print_json(result)
        return 0
    except (BundleValidationError, KeyError, RuntimeError, ValueError, OSError) as exc:
        print(f"palgwae: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

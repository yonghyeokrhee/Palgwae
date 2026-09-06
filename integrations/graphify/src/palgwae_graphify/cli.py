from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .adapter import adapt_graph, write_candidate_ledger
from .runner import GRAPHIFY_VERSION, run_graphify


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="palgwae-graphify")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="run isolated code-only extraction")
    extract.add_argument("--repo-root", type=Path, required=True)
    extract.add_argument("--repository", required=True)
    extract.add_argument("--revision", required=True)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--executable", default="graphify")
    extract.add_argument("--max-workers", type=int, default=1)

    adapt = commands.add_parser("adapt", help="convert graph.json to candidates")
    adapt.add_argument("--graph", type=Path, required=True)
    adapt.add_argument("--repo-root", type=Path, required=True)
    adapt.add_argument("--repository", required=True)
    adapt.add_argument("--revision", required=True)
    adapt.add_argument("--output", type=Path, required=True)
    adapt.add_argument("--graphify-version", default=GRAPHIFY_VERSION)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "extract":
            result = run_graphify(
                repo_root=args.repo_root,
                repository=args.repository,
                revision=args.revision,
                output_dir=args.output,
                executable=args.executable,
                max_workers=args.max_workers,
            )
        else:
            graph = json.loads(args.graph.read_text(encoding="utf-8"))
            ledger = adapt_graph(
                graph,
                repository=args.repository,
                revision=args.revision,
                repo_root=args.repo_root,
                graphify_version=args.graphify_version,
            )
            result = write_candidate_ledger(ledger, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (FileExistsError, OSError, RuntimeError, ValueError) as exc:
        print(f"palgwae-graphify: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

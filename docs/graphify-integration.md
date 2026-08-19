# Graphify integration boundary

Graphify and Palgwae solve different parts of the problem:

- Graphify discovers broad code relationships quickly.
- Palgwae decides which data-engineering relationships are safe to traverse.

The dependency points in one direction only:

```text
Graphify graph.json
  -> Palgwae candidate adapter
  -> candidate ledger
  -> explicit resolution and verification (future)
  -> accepted Palgwae bundle
  -> MCP query
```

Graphify cannot write `nodes.jsonl`, `claims.jsonl`, or `evidence.jsonl` in an
accepted bundle. Its candidate identifiers are not canonical entity IDs, and
its confidence labels are not Palgwae review decisions.

## Why it is a separate project

`integrations/graphify` has its own `pyproject.toml` and `uv.lock`. This keeps
the root installation small, lets the MCP runtime start without Graphify, and
contains extractor version changes to one compatibility surface.

## Security defaults

- exact Graphify version pin;
- offline `--code-only` extraction;
- clean repository at a 40-character Git revision;
- output outside the scanned repository;
- environment allowlist instead of a secret denylist;
- no automatic extraction from an MCP query;
- no raw or candidate artifacts committed by default.

## Current limit

Version 0.2 provides extraction and deterministic candidate adaptation, not
automatic promotion. This is intentional: candidate coverage can be measured
without weakening the accepted graph's evidence contract.

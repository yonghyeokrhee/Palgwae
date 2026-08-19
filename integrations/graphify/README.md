# Optional Graphify candidate extractor

This is a separate build-time project. The Palgwae runtime and MCP server do
not depend on Graphify.

Graphify is pinned to `graphifyy[sql,terraform]==0.9.46`. It runs in code-only
mode with a minimal environment allowlist, a clean pinned Git revision, and an
output directory outside the scanned repository. Ambient API, cloud, SSH, and
agent credentials are not forwarded.

```bash
cd integrations/graphify
uv sync --frozen

REVISION=$(git -C /path/to/project rev-parse HEAD)
uv run palgwae-graphify extract \
  --repo-root /path/to/project \
  --repository example-project \
  --revision "$REVISION" \
  --output /path/outside/project/graphify-run

uv run palgwae-graphify adapt \
  --graph /path/outside/project/graphify-run/raw/graphify-out/graph.json \
  --repo-root /path/to/project \
  --repository example-project \
  --revision "$REVISION" \
  --output /path/outside/project/candidate-ledger
```

The output is deliberately not a Palgwae accepted graph. All claims have
`review_status=CANDIDATE`, all endpoints use extractor-scoped candidate IDs,
and the manifest declares `accepted_claim_count=0`.

A future promotion command must resolve candidate endpoints to an external
canonical registry and run predicate-specific source verification. Until that
exists, candidate ledgers are for review and coverage analysis only.

# Contributing

Thanks for helping Palgwae make data-pipeline context safer for developers and
agents.

## Start small

Open an issue before a broad ontology or storage change. Adapter, relation, and
Golden-test pull requests should each solve one reviewable problem.

Good first pull requests include:

- one new fictional example;
- one adapter emitting candidates;
- one negative test that preserves `UNKNOWN`;
- one documentation clarification;
- one static visualization.

## Development

```bash
git clone https://github.com/yonghyeokrhee/Palgwae.git
cd Palgwae
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Or use uv:

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run ruff check src tests scripts integrations/graphify/src integrations/graphify/tests
uv run --project integrations/graphify python -m unittest discover -s integrations/graphify/tests -v
uv run python scripts/check_release.py
```

## Pull request checklist

- [ ] No private repository names, credentials, account IDs, or production data
- [ ] New claims have reproducible evidence
- [ ] Relation direction follows `docs/ontology.md`
- [ ] Empty traversal remains `UNKNOWN`
- [ ] Tests cover both positive and negative behavior
- [ ] Generated bundles pass `palgwae doctor`
- [ ] Public behavior is documented

## Adapter design

Adapters emit candidates. Promotion belongs to a separate, named verification
gate. The Airflow adapter's gate accepts only the documented AST rules and
checks endpoint types, DAG scope, and evidence. Include a small synthetic
fixture and an unsupported case. Never copy private DAGs into tests.

The installed-wheel workflow is in `.github/workflows/test.yml`. New behavior
should work outside an editable checkout. Python runtime version comes from
installed package metadata; release-facing plugin/npm versions are checked by
`scripts/check_release.py`. See `docs/releasing.md` before changing them.

Read CODE_OF_CONDUCT.md and GOVERNANCE.md. Work through a pull request and
include the relevant checks. The maintainer is responsible for releases;
there is no additional CLA or fixed review SLA.

## License

By contributing, you agree that your contribution is licensed under Apache-2.0.

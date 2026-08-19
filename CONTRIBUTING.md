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
uv sync
uv run python -m unittest discover -s tests -v
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

Adapters emit candidates. They must not directly promote claims into the
accepted bundle. Include a fixture small enough to review in the pull request.

## License

By contributing, you agree that your contribution is licensed under Apache-2.0.

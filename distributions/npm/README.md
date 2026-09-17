# Palgwae CLI

Trace declared Airflow dependencies with pinned source evidence. The CLI runs
locally and never imports DAGs. Requires Node 20+ (or Bun) and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

This package bundles the matching Python wheel and starts it through uv's cached
tool environment. It has no JavaScript dependencies or installation scripts.
First execution may download Python and Python dependencies; later executions
reuse the environment. There is no claim that the graph engine runs faster in Bun.

Install a GitHub release tarball using npm, pnpm, or Bun. See the repository's
[installation guide](https://github.com/yonghyeokrhee/Palgwae/blob/main/docs/installation.md).
The npm registry name is reserved here as release metadata; use a GitHub archive
until a registry release is listed in the release notes.

```sh
palgwae example
palgwae init --source palgwae-example --namespace urn:example:palgwae:airflow
palgwae find publish --bundle .palgwae/bundle
```

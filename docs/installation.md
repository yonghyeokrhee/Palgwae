# Install Palgwae

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then choose
one CLI installation. The engine requires Python 3.11+; uv manages its environment.

| Channel | Use it for |
| --- | --- |
| GitHub v0.3.0 wheel | Stable single-repository Airflow extraction |
| Current source checkout | Multi-repository workspaces and contributing |

Agent plugins and MCP client files do not install the CLI or generate a bundle.
Install the engine first, run `init`, then connect the printed MCP configuration.

## Python / uv

```sh
uv tool install https://github.com/yonghyeokrhee/Palgwae/releases/download/v0.3.0/palgwae-0.3.0-py3-none-any.whl
palgwae --version
```

If the shell cannot find `palgwae`, run `uv tool update-shell` and restart your
terminal. This uses the wheel from the [0.3.0 prerelease](https://github.com/yonghyeokrhee/Palgwae/releases/tag/v0.3.0).

The project is not yet published on PyPI. Do not rely on `pip install palgwae`
until a release explicitly announces that channel. The wheel also works with
pip in your own virtual environment.

## Current source: multi-repository workspaces

Until the workspace feature receives a versioned release, install a reviewed
source checkout explicitly. Check out the branch or commit containing workspace
support before installing it:

```sh
git clone https://github.com/yonghyeokrhee/Palgwae.git
cd Palgwae
uv sync --frozen
uv tool install --force .
palgwae --version
```

`uv sync --frozen` creates the contributor/test environment. `uv tool install`
creates the standalone command used from other project directories. If you do
not want a tool installation, replace `palgwae` in the examples with:

```sh
uv run --project /path/to/Palgwae palgwae
```

Check out the related repositories before initialization. Palgwae does not clone
them or discover private repositories automatically:

```text
work/
  pipeline/
  airflow/
  backend/
```

```sh
cd work/pipeline
palgwae init \
  --repo pipeline=. \
  --repo airflow=../airflow \
  --repo backend=../backend \
  --namespace urn:example:team:data-platform \
  --environment prd
palgwae doctor --bundle .palgwae/bundle
```

The `environment` value selects supported source configuration; it does not
contact that environment. Continue with the [workspace guide](workspaces.md)
and [agent setup](cross-agent-plugins.md).

## pnpm, Bun, or npm

The npm-format release archive bundles the same Python wheel. It requires uv
and Node 20+ (or Bun). Choose one:

```sh
pnpm add -g https://github.com/yonghyeokrhee/Palgwae/releases/download/v0.3.0/yonghyeokrhee-palgwae-0.3.0.tgz
# or
bun add -g https://github.com/yonghyeokrhee/Palgwae/releases/download/v0.3.0/yonghyeokrhee-palgwae-0.3.0.tgz
# or
npm install -g https://github.com/yonghyeokrhee/Palgwae/releases/download/v0.3.0/yonghyeokrhee-palgwae-0.3.0.tgz
```

There are no JavaScript dependencies or installation scripts. On first execution,
uv creates a cached Python environment; later invocations reuse it. This is a
distribution choice, not a claim that Bun accelerates Python analysis. npm
registry publication is separate and requires publishing credentials.

If pnpm reports a missing global bin directory, run `pnpm setup` as it advises
and restart the terminal. For a non-global test, download the release archive
and run `pnpm --package ./yonghyeokrhee-palgwae-0.3.0.tgz dlx palgwae --help`.

## First stable-release result

```sh
palgwae example
palgwae init --source palgwae-example --namespace urn:example:palgwae:airflow
palgwae find publish --bundle .palgwae/bundle
palgwae downstream urn:example:palgwae:airflow/task/daily_orders/publish --bundle .palgwae/bundle
```

Expected: a declared dependency from publish through a sensor to a reporting
task. `example` refuses to overwrite an existing example file. No Airflow
scheduler is needed. `init` writes a bundle and prints MCP settings; it does not
modify your agent configuration automatically.

For real v0.3.0 data, use your DAG directory and a namespace you control. See
[Airflow support](airflow.md) and [agent setup](cross-agent-plugins.md).

## Upgrade and remove

Install the next release with the same package manager. Review CHANGELOG.md,
rebuild the graph, and restart MCP so it loads the new snapshot.

Remove using `uv tool uninstall palgwae`, `pnpm remove -g @yonghyeokrhee/palgwae`,
`bun remove -g @yonghyeokrhee/palgwae`, or `npm uninstall -g @yonghyeokrhee/palgwae`,
matching your installation. Remove the plugin through its host. Generated
directories remain yours to retain or delete.

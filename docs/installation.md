# Install Palgwae

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then choose
one CLI installation. The engine requires Python 3.11+; uv manages its environment.

## Python / uv

```sh
uv tool install https://github.com/yonghyeokrhee/Palgwae/releases/download/v0.3.0/palgwae-0.3.0-py3-none-any.whl
palgwae --version
```

If the shell cannot find `palgwae`, run `uv tool update-shell` and restart your
terminal. This uses the wheel from the [0.3.0 prerelease](https://github.com/yonghyeokrhee/Palgwae/releases/tag/v0.3.0).
Before the release exists, use the source-checkout workflow:

```sh
git clone https://github.com/yonghyeokrhee/Palgwae.git
cd Palgwae
uv sync --frozen
uv run palgwae --help
```

The project is not yet published on PyPI. Do not rely on `pip install palgwae`
until a release explicitly announces that channel. The wheel also works with
pip in your own virtual environment.

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

## First result

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

For real data, use your DAG directory and a namespace you control. See
[Airflow support](airflow.md) and [agent setup](cross-agent-plugins.md).

## Upgrade and remove

Install the next release with the same package manager. Review CHANGELOG.md,
rebuild the graph, and restart MCP so it loads the new snapshot.

Remove using `uv tool uninstall palgwae`, `pnpm remove -g @yonghyeokrhee/palgwae`,
`bun remove -g @yonghyeokrhee/palgwae`, or `npm uninstall -g @yonghyeokrhee/palgwae`,
matching your installation. Remove the plugin through its host. Generated
directories remain yours to retain or delete.

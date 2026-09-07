# Releasing

Keep pyproject, both plugin manifests, and npm package versions aligned. Python
reports its installed metadata version; Graphify has a separate package lifecycle.

Run CI, the installed-wheel smoke test, dependency audit, and
`scripts/check_release.py`. Inspect release archives and documentation. Tag only
the reviewed, passing commit; never move an existing public release tag.

`release.yml` builds a wheel, source archive, npm tarball, and SHA256SUMS, tests
the installed wheel, then publishes a GitHub prerelease when a `v*` tag is pushed.
A manual run builds artifacts without publishing.

The Claude Code catalog distributes the plugin through this repository. The
OpenAI repo catalog is a local/team source, not a public directory approval.
See [client distribution](cross-agent-plugins.md).

## Optional registry channels

GitHub authentication does not grant npm or PyPI publishing rights. To add
PyPI, register a pending Trusted Publisher for a dedicated workflow/environment
and use PyPA's publishing action with job-scoped `id-token: write`. Start on
TestPyPI and keep the publication job separate from PR jobs. See
[PyPI's guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

For npm, authenticate the publisher or configure trusted publishing. Verify
ownership of `@yonghyeokrhee/palgwae` and inspect `npm pack` before publication.
Do not announce registry commands until that version is downloadable. GitHub
release archives work independently of both registries.

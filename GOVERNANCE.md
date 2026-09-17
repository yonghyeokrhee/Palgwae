# Governance

Palgwae is maintained by [yonghyeokrhee](https://github.com/yonghyeokrhee).
The maintainer reviews contributions, decides releases, and resolves design
disagreements in public issues or pull requests. This is currently a single-
maintainer project; there is no implied commercial support team.

Discuss changes to canonical identity, ontology direction, accepted evidence,
or bundle compatibility before implementation. A proposal should show a real
use case, a redistributable fixture, and a case that must remain `UNKNOWN`.
Small adapters and tests are welcome without a formal RFC process.

During 0.x, new CLI behavior may change between minor releases. Breaking changes
must be called out in the changelog. Bundle schema and adapter policy versions
are separate from the package version. A changed acceptance rule requires
rebuilding and comparing results before deploying it to a team's workflow.

Contributions are licensed under Apache-2.0 as described in CONTRIBUTING.md.
There is no additional CLA. Sustained contributors can discuss a maintainer
role through an issue; no automatic promotion or review deadline is promised.

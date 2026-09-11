# Data handling

Palgwae's core CLI and Airflow extractor operate on local files. They do not
send telemetry or source code to a service. There is no Palgwae cloud account.
Installing the CLI, or first running the npm launcher through uv, downloads
packages from configured registries and may download Python.

Bundles may store repository names, DAG/task and infrastructure resource
identifiers, operator/import names, relative source paths, literal schedule
strings, selected environment labels, source hashes, line ranges, and graph
relationships. Workspace extraction deliberately omits source bodies, tfvars
values, SQL strings, connection payloads, credentials, and source excerpts.
These omissions do not make a bundle anonymous: identifiers and topology can
still be confidential.

`.palgwae/workspace.yaml` contains local relative checkout paths and registered
repository names. `.palgwae/` is ignored by default. Review both the workspace
file and bundle before deliberately sharing or force-adding either one.

MCP sends query results to the agent or app you connect. That host's data
policies and model-provider settings apply. Decide whether a bundle can be
shared before connecting it to a hosted agent, publishing it, or attaching it
to an issue. Use the packaged fictional example when testing public services.

The optional Graphify integration has a separate dependency set and execution
boundary described in [graphify-integration.md](graphify-integration.md).

Delete your generated bundle directory to remove Palgwae's local graph output.
Your package manager and uv manage their own caches separately. The `example`
command creates a fictional source directory; it is independent of your DAGs.

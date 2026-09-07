# Data handling

Palgwae's core CLI and Airflow extractor operate on local files. They do not
send telemetry or source code to a service. There is no Palgwae cloud account.
Installing the CLI, or first running the npm launcher through uv, downloads
packages from configured registries and may download Python.

The Airflow bundle stores DAG/task identifiers, operator import names, relative
source paths, literal schedule strings, source hashes, line ranges, and
relationships. It deliberately omits callable bodies, SQL strings, connection
payloads, environment values, and source excerpts. These omissions do not make
a bundle anonymous: its identifiers and topology can still be confidential.

MCP sends query results to the agent or app you connect. That host's data
policies and model-provider settings apply. Decide whether a bundle can be
shared before connecting it to a hosted agent, publishing it, or attaching it
to an issue. Use the packaged fictional example when testing public services.

The optional Graphify integration has a separate dependency set and execution
boundary described in [graphify-integration.md](graphify-integration.md).

Delete your generated bundle directory to remove Palgwae's local graph output.
Your package manager and uv manage their own caches separately. The `example`
command creates a fictional source directory; it is independent of your DAGs.

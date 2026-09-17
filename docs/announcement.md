# Draft announcement for developers and data engineers

Palgwae makes declared Airflow dependencies available to your coding agent,
with source evidence attached.

When a publishing task changes, affected work may sit in another DAG behind an
ExternalTaskSensor. Palgwae reads DAG source, builds a portable local graph,
and lets you ask which tasks are downstream and where the relationships were
declared. It records the boundaries it could not resolve.

The 0.3 alpha supports a documented subset of classic Airflow and TaskFlow.
It parses source without importing DAGs or running jobs. No Airflow deployment,
graph database, API key, or model call is required for extraction and traversal.
CLI and MCP queries use the same snapshot.

Install a GitHub release wheel or npm-format archive, then connect the Claude
Code or Codex plugin. Try the packaged fictional example first; the installation
guide explains the exact commands and support boundaries.

This early alpha is for source review. It does not establish that a pipeline
ran successfully. Dynamic Python, TaskGroups, repeated TaskFlow names, Spark
plans, and SQL lineage still need further work.

We welcome small synthetic reproductions, unsupported-pattern reports, and
predicate-specific adapters. A contribution can be one dependency we can prove,
or one case where we should explicitly say “unknown.”

Repository: https://github.com/yonghyeokrhee/Palgwae

This reusable draft has not been posted or sent to anyone. Verify the announced
release is live before posting.

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from palgwae.workspace_resources import extract_resources


DECLARATION = '''resource "aws_glue_job" "jobs" {
  for_each = var.glue.jobs
  name = each.key
}
resource "aws_lambda_function" "functions" {
  for_each = var.services.functions
  function_name = each.key
}
'''


class WorkspaceResourcesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def extract(self, environment="prd"):
        return extract_resources(self.root, "urn:example:infra", environment)

    def resources(self, bundle):
        return [n for n in bundle.nodes if n.attributes.get("resource_kind")]

    def test_selected_map_registration_and_full_file_evidence(self):
        self.put("terraform/main.tf", DECLARATION)
        self.put("terraform/configurations/prd.tfvars", 'glue = { jobs = { nightly = { password = "SECRET" } } }\nservices = { functions = { dispatch = {} } }')
        self.put("terraform/configurations/dev.tfvars", 'glue = { jobs = { sandbox = {} } }')
        bundle, refs, coverage = self.extract()
        self.assertEqual({n.name for n in self.resources(bundle)}, {"nightly", "dispatch"})
        self.assertEqual(coverage["resources"], 2)
        self.assertFalse(refs)
        for claim in bundle.claims:
            self.assertEqual(claim.assertion_kind, "DECLARED")
            self.assertEqual(claim.review_status, "AUTO_VERIFIED")
            self.assertEqual(len(claim.evidence_ids), 2)
        for evidence in bundle.evidence:
            digest = hashlib.sha256((self.root / evidence.path).read_bytes()).hexdigest()
            self.assertEqual(evidence.content_hash, digest)
            self.assertRegex(evidence.revision, r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(evidence.locator, r"^L1-L\d+$")
        serialized = json.dumps([n.to_dict() for n in bundle.nodes] + [e.to_dict() for e in bundle.evidence])
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("password", serialized)
        self.assertEqual(len({e.revision for e in bundle.evidence}), 1)
        original_revision = bundle.evidence[0].revision
        self.put("terraform/configurations/prd.tfvars", 'glue = { jobs = { replaced = {} } }\nservices = { functions = { dispatch = {} } }')
        revised, _, _ = self.extract()
        self.assertTrue(all(e.revision != original_revision for e in revised.evidence))
        old_source_hash = next(e.content_hash for e in bundle.evidence if e.path.endswith("main.tf"))
        self.assertEqual(next(e.content_hash for e in revised.evidence if e.path.endswith("main.tf")), old_source_hash)

    def test_environment_is_not_guessed_and_dev_is_separate(self):
        self.put("terraform/main.tf", DECLARATION)
        self.put("terraform/configurations/prd.tfvars", 'glue = { jobs = { prod_only = {} } }')
        self.put("terraform/configurations/dev.tfvars", 'glue = { jobs = { dev_only = {} } }')
        self.assertEqual([n.name for n in self.resources(self.extract("dev")[0])], ["dev_only"])
        bundle, _, _ = self.extract(None)
        self.assertFalse(self.resources(bundle))
        self.assertTrue(bundle.unresolved)

    def test_module_local_and_ambiguous_variable_sources(self):
        self.put("module/main.tf", DECLARATION)
        self.put("elsewhere/prd.tfvars", 'glue = { jobs = { unrelated = {} } }')
        self.assertFalse(self.resources(self.extract()[0]))
        self.put("module/prd.tfvars", 'glue = { jobs = { first = {} } }')
        self.put("module/terraform.tfvars", 'glue = { jobs = { second = {} } }')
        bundle, _, _ = self.extract()
        self.assertFalse(self.resources(bundle))
        self.assertTrue(any("unique" in u.reason for u in bundle.unresolved))

    def test_dynamic_names_counts_and_expressions_are_not_resources(self):
        self.put("main.tf", '''resource "aws_glue_job" "dynamic" { name = var.name }
resource "aws_glue_job" "disabled" { name = "disabled"\n count = 0 }
resource "aws_glue_job" "computed" { name = each.key\n for_each = toset(var.names) }
resource "aws_lambda_function" "literal" { function_name = "direct" }
''')
        bundle, _, _ = self.extract()
        self.assertEqual([n.name for n in self.resources(bundle)], ["direct"])
        self.assertEqual(len(bundle.unresolved), 2)

    def test_duplicate_names_keep_distinct_declarations(self):
        self.put("a.tf", 'resource "aws_glue_job" "one" { name = "nightly" }')
        self.put("b.tf", 'resource "aws_glue_job" "two" { name = "nightly" }')
        bundle, _, _ = self.extract()
        nodes = self.resources(bundle)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(len({n.node_id for n in nodes}), 2)

    def test_boto3_verified_receivers_and_source_only_execution(self):
        self.put("backend.py", '''import boto3 as aws
from boto3 import client as make_client
glue = aws.client("glue")
lambda_client = make_client("lambda")
raise RuntimeError("MUST NOT EXECUTE")
def handler(event):
    glue.start_job_run(JobName="nightly")
    lambda_client.invoke(FunctionName="dispatch")
''')
        bundle, refs, coverage = self.extract()
        self.assertEqual({r["target_name"] for r in refs}, {"nightly", "dispatch"})
        self.assertEqual(coverage["sdk_references"], 2)
        self.assertTrue(all(n.node_type in {"Repository", "Script"} for n in bundle.nodes))
        self.assertTrue(all(e.attributes["locator_verified"] for e in bundle.evidence))

    def test_spoofed_rebound_shadowed_and_dynamic_receivers_are_unknown(self):
        self.put("backend.py", '''import boto3
glue = boto3.client("glue")
def shadow(glue):
    glue.start_job_run(JobName="parameter")
def rebound():
    client = boto3.client("glue")
    client = fake()
    client.start_job_run(JobName="rebound")
def branch():
    if flag:
        glue = fake()
    glue.start_job_run(JobName="branch")
other.start_job_run(JobName="spoofed")
glue.start_job_run(JobName=dynamic())
''')
        bundle, refs, _ = self.extract()
        self.assertFalse(refs)
        self.assertEqual(len(bundle.unresolved), 5)

    def test_class_attribute_does_not_become_bare_method_binding(self):
        self.put("backend.py", '''import boto3
class Worker:
    glue = boto3.client("glue")
    def run(self):
        glue.start_job_run(JobName="wrong_scope")
''')
        self.assertFalse(self.extract()[1])

    def test_monkeypatched_client_factory_is_unresolved(self):
        self.put("backend.py", '''import boto3
boto3.client = fake
glue = boto3.client("glue")
glue.start_job_run(JobName="spoofed")
''')
        self.assertFalse(self.extract()[1])

    def test_wildcard_import_invalidates_local_and_inherited_sdk_bindings(self):
        self.put("backend.py", '''import boto3
from boto3 import client
glue = client("glue")
from custom import *
glue.start_job_run(JobName="module_call")
def inherited_client():
    glue.start_job_run(JobName="inherited_client")
def inherited_package():
    local_client = boto3.client("glue")
    local_client.start_job_run(JobName="inherited_package")
''')
        bundle, refs, _ = self.extract()
        self.assertFalse(refs)
        self.assertEqual(len(bundle.unresolved), 3)

    def test_unvisited_defaults_and_explicit_connection_scope_are_unknown(self):
        self.put("backend.py", '''import boto3
glue = boto3.client("glue", region_name="eu-west-1")
glue.start_job_run(JobName="other_region")
def run(value=glue.start_job_run(JobName="default")):
    pass
''')
        bundle, refs, _ = self.extract()
        self.assertFalse(refs)
        self.assertEqual(len(bundle.unresolved), 2)

    def test_provider_alias_and_automatic_variable_override_are_unknown(self):
        self.put("main.tf", DECLARATION + '\nresource "aws_glue_job" "remote" { name = "remote"\n provider = aws.other }')
        self.put("prd.tfvars", 'glue = { jobs = { selected = {} } }')
        self.put("override.auto.tfvars.json", '{"glue": {"jobs": {"override": {}}}}')
        bundle, _, _ = self.extract()
        self.assertFalse(self.resources(bundle))
        self.assertTrue(any("provider" in u.reason for u in bundle.unresolved))

    def test_terraform_overrides_cannot_publish_superseded_resource_edges(self):
        from palgwae.bundle import GraphBundle
        from palgwae.workspace import build_workspace, initialize_workspace

        for index, filename in enumerate([
            "override.tf", "custom_override.tf", "override.tf.json", "custom_override.tf.json"
        ]):
            prefix = f"module_{index}"
            self.put(prefix + "/main.tf", f'resource "aws_glue_job" "job" {{ name = "old_{index}" }}')
            replacement = (
                json.dumps({"resource": {"aws_glue_job": {"job": {"name": f"new_{index}"}}}})
                if filename.endswith(".json") else
                f'resource "aws_glue_job" "job" {{ name = "new_{index}" }}'
            )
            self.put(prefix + "/" + filename, replacement)
        self.put("unaffected/main.tf", 'resource "aws_glue_job" "job" { name = "kept" }')
        self.put("backend.py", '''import boto3
client = boto3.client("glue")
client.start_job_run(JobName="old_0")
client.start_job_run(JobName="kept")
''')
        bundle, _, _ = self.extract()
        self.assertEqual([node.name for node in self.resources(bundle)], ["kept"])
        self.assertTrue(any("override" in gap.reason for gap in bundle.unresolved))
        config = initialize_workspace(self.root, ["infra=."], "urn:example:workspace", "prd")
        build_workspace(config)
        published = GraphBundle.load(self.root / ".palgwae" / "bundle")
        names = {node.node_id: node.name for node in published.nodes}
        self.assertEqual(
            [names[claim.object] for claim in published.claims if claim.predicate == "INVOKES"],
            ["kept"],
        )
        self.assertTrue(any(gap.target_hint == "old_0" for gap in published.unresolved))

    def test_terraform_json_configuration_blocks_only_its_module(self):
        self.put("affected/main.tf", 'resource "aws_glue_job" "job" { name = "not_proven" }')
        self.put("affected/provider.tf.json", '{"provider": {"aws": {"region": "us-east-1"}}}')
        self.put("unaffected/main.tf", 'resource "aws_glue_job" "job" { name = "kept" }')
        bundle, _, _ = self.extract()
        self.assertEqual([node.name for node in self.resources(bundle)], ["kept"])
        self.assertTrue(any("JSON configuration" in gap.reason for gap in bundle.unresolved))

    def test_generated_sources_and_symlinks_are_excluded(self):
        for prefix in ["docs", "archive", "output", ".palgwae", ".worktrees", ".venv", "tests", "fixtures", "examples", "vendor"]:
            self.put(prefix + "/hidden.tf", 'resource "aws_glue_job" "hidden" { name = "hidden" }')
        path = self.put("safe.tf", 'resource "aws_glue_job" "safe" { name = "safe" }')
        (self.root / "linked.tf").symlink_to(path)
        self.assertEqual([n.name for n in self.resources(self.extract()[0])], ["safe"])


if __name__ == "__main__":
    unittest.main()

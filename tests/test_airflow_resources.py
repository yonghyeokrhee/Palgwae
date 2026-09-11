import tempfile
import unittest
from pathlib import Path

from palgwae.airflow import extract_airflow
from palgwae.bundle import BundleValidationError


class AirflowResourceTest(unittest.TestCase):
    def extract(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pipeline.py").write_text(source)
            return extract_airflow(root, "urn:example:airflow")

    def test_imported_aliases_make_candidate_references_only(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator as Glue
import airflow.providers.amazon.aws.operators.lambda_function as lambdas
with DAG("daily"):
    run = Glue(task_id="run", job_name="warehouse_build")
    notify = lambdas.LambdaInvokeFunctionOperator(task_id="notify", function_name="notify_ready")
    run >> notify
''')
        references = result.resource_references
        self.assertEqual(len(references), 2)
        self.assertEqual(references[0], {
            "subject": result.tasks[("daily", "run")],
            "predicate": "STARTS",
            "target_kind": "aws_glue_job",
            "target_name": "warehouse_build",
            "evidence_ids": references[0]["evidence_ids"],
            "environment": None,
        })
        self.assertEqual(references[1]["target_kind"], "aws_lambda_function")
        self.assertEqual(references[1]["target_name"], "notify_ready")
        bundle = result.promote()
        self.assertFalse(any(claim.predicate == "STARTS" for claim in bundle.claims))
        self.assertFalse(any(node.name == "warehouse_build" for node in bundle.nodes))
        self.assertEqual(sum(claim.predicate == "NEXT" for claim in bundle.claims), 1)
        self.assertFalse(bundle.unresolved)

    def test_spoofed_and_shadowed_operators_have_no_resource_reference(self):
        result = self.extract('''from airflow import DAG
from foreign import GlueJobOperator
from airflow.fake import LambdaInvokeFunctionOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator as RealGlue
RealGlue = replacement
with DAG("daily"):
    first = GlueJobOperator(task_id="first", job_name="fake")
    second = LambdaInvokeFunctionOperator(task_id="second", function_name="fake")
    third = RealGlue(task_id="third", job_name="fake")
''')
        self.assertEqual(result.resource_references, [])

    def test_relative_import_cannot_spoof_absolute_airflow_class(self):
        result = self.extract('''from airflow import DAG
from .airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    first = GlueJobOperator(task_id="first", job_name="fake")
''')
        self.assertEqual(result.resource_references, [])

    def test_wildcard_import_invalidates_operator_identity(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    from custom import *
    run = GlueJobOperator(task_id="run", job_name="fake")
''')
        self.assertFalse(result.resource_references)
        self.assertTrue(result.promote().unresolved)

    def test_unresolved_connection_scope_has_no_resource_reference(self):
        arguments = [
            'region_name="us-east-1"',
            'region_name=None',
            'aws_conn_id="other_account"',
            'aws_conn_id=get_connection()',
            'botocore_config={"region_name": "us-east-1"}',
            'default_args={"aws_conn_id": "other_account"}',
            '**extra_arguments',
        ]
        for argument in arguments:
            with self.subTest(argument=argument):
                result = self.extract(f'''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    run = GlueJobOperator(task_id="run", job_name="build", {argument})
''')
                self.assertEqual(result.resource_references, [])
                self.assertEqual(len(result.promote().unresolved), 1)

    def test_dag_inherited_or_dynamic_connection_defaults_are_unresolved(self):
        for defaults in [
            '{"aws_conn_id": "other_account"}',
            '{"region_name": "us-east-1"}',
            'shared_defaults',
            '{**shared_defaults}',
        ]:
            with self.subTest(defaults=defaults):
                result = self.extract(f'''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily", default_args={defaults}):
    run = GlueJobOperator(task_id="run", job_name="build")
''')
                self.assertFalse(result.resource_references)
                self.assertEqual(len(result.promote().unresolved), 1)

    def test_inline_non_scope_defaults_preserve_declaration_evidence(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily", default_args={"owner": "team", "retries": 2, "aws_conn_id": "aws_default"}):
    run = GlueJobOperator(task_id="run", job_name="build")
''')
        self.assertEqual(len(result.resource_references), 1)
        self.assertEqual(len(result.resource_references[0]["evidence_ids"]), 2)
        self.assertFalse(result.promote().unresolved)

    def test_explicit_default_connection_keeps_candidate_reference(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.lambda_function import LambdaInvokeFunctionOperator
with DAG("daily"):
    run = LambdaInvokeFunctionOperator(task_id="run", function_name="notify", aws_conn_id="aws_default")
''')
        self.assertEqual(len(result.resource_references), 1)
        self.assertFalse(result.promote().unresolved)

    def test_dynamic_or_absent_targets_remain_unresolved(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.operators.lambda_function import LambdaInvokeFunctionOperator
with DAG("daily"):
    dynamic = GlueJobOperator(task_id="dynamic", job_name=resolve_job())
    missing = LambdaInvokeFunctionOperator(task_id="missing")
''')
        self.assertEqual(result.resource_references, [])
        bundle = result.promote()
        self.assertEqual(len(bundle.unresolved), 2)
        self.assertEqual(
            {gap.source_node_id for gap in bundle.unresolved},
            set(result.tasks.values()),
        )

    def test_resource_evidence_survives_without_local_claims(self):
        result = self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    run = GlueJobOperator(task_id="run", job_name="warehouse_build")
''')
        result.candidates.clear()
        bundle = result.promote()
        self.assertEqual(
            {evidence.evidence_id for evidence in bundle.evidence},
            set(result.resource_references[0]["evidence_ids"]),
        )
        self.assertTrue(all(e.attributes["locator_verified"] for e in bundle.evidence))

    def test_dynamic_task_or_unparsed_source_never_produces_reference(self):
        sources = [
            '''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    run = GlueJobOperator(task_id=resolve_task(), job_name="warehouse_build")
''',
            '''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    run = GlueJobOperator(task_id="run", job_name="warehouse_build")
this is not valid python !
''',
        ]
        for source in sources:
            with self.subTest(source=source):
                result = self.extract(source)
                self.assertEqual(result.resource_references, [])
                self.assertTrue(result.promote().unresolved)

    def test_duplicate_task_identity_still_fails(self):
        with self.assertRaises(BundleValidationError):
            self.extract('''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    first = GlueJobOperator(task_id="run", job_name="first")
    second = GlueJobOperator(task_id="run", job_name="second")
''')


if __name__ == "__main__":
    unittest.main()

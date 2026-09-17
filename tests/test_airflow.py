import tempfile
import unittest
from pathlib import Path

from palgwae.airflow import build_airflow, extract_airflow
from palgwae.bundle import BundleValidationError, GraphBundle
from palgwae.graph import ContextGraph


CLASSIC = """from airflow import DAG
from airflow.operators.empty import EmptyOperator as Op
from airflow.sensors.external_task import ExternalTaskSensor

with DAG("warehouse", schedule="@daily") as dag:
    extract = Op(task_id="extract")
    transform = Op(task_id="transform")
    check = Op(task_id="check")
    publish = Op(task_id="publish")
    extract >> [transform, check] >> publish
with DAG("consumer"):
    wait = ExternalTaskSensor(task_id="wait", external_dag_id="warehouse", external_task_id="publish")
    consume = Op(task_id="consume")
    consume.set_upstream(wait)
"""


class AirflowTest(unittest.TestCase):
    def extract(self, text):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "pipeline.py").write_text(text)
        return extract_airflow(root, "urn:example:palgwae:airflow"), root

    def test_classic_fanout_sensor_and_query(self):
        result, root = self.extract(CLASSIC)
        report = build_airflow(root, root / "bundle", result.namespace)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["extraction"]["tasks"], 6)
        self.assertEqual(report["warnings"], [])
        bundle = GraphBundle.load(root / "bundle")
        graph = ContextGraph(bundle)
        source = result.tasks[("warehouse", "extract")]
        target = result.tasks[("consumer", "consume")]
        self.assertEqual(graph.path(source, target)["status"], "ANSWERED")
        self.assertEqual(sum(c.predicate == "NEXT" for c in bundle.claims), 5)
        self.assertEqual(sum(c.predicate == "WAITS_FOR" for c in bundle.claims), 1)
        first = report["bundle_digest"]
        self.assertEqual(
            build_airflow(root, root / "again", result.namespace)["bundle_digest"], first
        )

    def test_taskflow_nested_calls_and_aliases(self):
        result, _ = self.extract("""from airflow.sdk import dag, task
@dag(schedule="@daily")
def daily():
    @task
    def extract(): return {"total": 1}
    @task()
    def load(value): pass
    load(extract()["total"])
daily()
""")
        bundle = result.promote()
        self.assertEqual(len(result.tasks), 2)
        self.assertEqual(sum(c.predicate == "NEXT" for c in bundle.claims), 1)

    def test_unknowns_and_no_execution(self):
        result, root = self.extract("""from airflow import DAG
from airflow.operators.empty import EmptyOperator
raise RuntimeError("MUST NEVER EXECUTE")
with DAG("daily"):
    a = EmptyOperator(task_id="a")
    b = EmptyOperator(task_id=get_id())
    a >> b
    for x in range(10):
        generated = EmptyOperator(task_id=f"task_{x}")
""")
        bundle = result.promote()
        self.assertEqual(len(result.tasks), 1)
        self.assertEqual(sum(c.predicate == "NEXT" for c in bundle.claims), 0)
        self.assertGreaterEqual(len(bundle.unresolved), 3)
        self.assertFalse((root / "executed").exists())

    def test_dynamic_rebinding_does_not_reuse_old_task(self):
        result, _ = self.extract(
            CLASSIC
            + """
if flag:
    extract = something_else()
extract >> publish
"""
        )
        bundle = result.promote()
        self.assertFalse(
            any(
                c.subject == result.tasks[("warehouse", "extract")]
                and c.object == result.tasks[("warehouse", "publish")]
                for c in bundle.claims
            )
        )
        self.assertTrue(bundle.unresolved)

    def test_no_foreign_operator_name_guessing(self):
        result, _ = self.extract("""from airflow import DAG
from not_airflow import FakeOperator
with DAG("daily"):
    a = FakeOperator(task_id="a")
""")
        self.assertEqual(len(result.tasks), 0)

    def test_duplicate_dags_and_invalid_namespace_fail(self):
        with self.assertRaises(BundleValidationError):
            self.extract(CLASSIC + '\nwith DAG("warehouse"): pass\n')
        _, root = self.extract(CLASSIC)
        with self.assertRaises(BundleValidationError):
            extract_airflow(root, "relative-name")

    def test_distinct_unknown_locations_survive(self):
        result, _ = self.extract(CLASSIC + "\nif x: pass\nif y: pass\n")
        bundle = result.promote()
        self.assertEqual(len(bundle.unresolved), 2)

    def test_list_to_list_is_not_claimed(self):
        result, _ = self.extract(CLASSIC + "\n[extract, transform] >> [check, publish]\n")
        self.assertEqual(len(result.promote().unresolved), 1)

    def test_explicit_dynamic_dag_does_not_use_context(self):
        result, _ = self.extract("""from airflow import DAG
from airflow.operators.empty import EmptyOperator
with DAG("daily"):
    a = EmptyOperator(task_id="a", dag=lookup())
""")
        self.assertEqual(len(result.tasks), 0)
        self.assertTrue(result.promote().unresolved)

    def test_classic_task_list_subscript_is_not_xcom(self):
        result, _ = self.extract(CLASSIC + "\nitems = [extract]\nitems[99] >> publish\n")
        self.assertTrue(result.promote().unresolved)
        self.assertFalse(
            any(
                c.predicate == "NEXT"
                and c.subject == result.tasks[("warehouse", "extract")]
                and c.object == result.tasks[("warehouse", "publish")]
                for c in result.promote().claims
            )
        )


if __name__ == "__main__":
    unittest.main()

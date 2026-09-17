"""Fictional pipeline. Palgwae reads this source without importing Airflow."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.decorators import dag, task


with DAG("daily_orders", schedule="@daily"):
    extract = EmptyOperator(task_id="extract")
    validate = EmptyOperator(task_id="validate")
    transform = EmptyOperator(task_id="transform")
    publish = EmptyOperator(task_id="publish")
    extract >> [validate, transform] >> publish

with DAG("reporting", schedule="@daily"):
    ready = ExternalTaskSensor(
        task_id="wait_for_orders",
        external_dag_id="daily_orders",
        external_task_id="publish",
    )
    report = EmptyOperator(task_id="report")
    ready >> report


@dag(schedule=None)
def metrics():
    @task
    def collect():
        return {"count": 1}

    @task
    def summarize(values):
        return values["count"]

    summarize(collect())


metrics()

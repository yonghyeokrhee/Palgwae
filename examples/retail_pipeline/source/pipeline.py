"""Fictional pipeline source used only as an extraction fixture."""

SCHEDULE = "0 2 * * *"
WORK_QUEUE = "orders-work"
READY_MARKER = "orders-daily-ready-v1"


def daily_orders_flow():
    trigger("daily_orders_schedule", cron=SCHEDULE)
    start("extract_orders", queue=WORK_QUEUE)
    run_after("build_orders_daily", "extract_orders")
    run_after("publish_orders", "build_orders_daily")


def extract_orders():
    read("object_store.raw_orders")
    write("lake.orders_bronze")


def publish_orders():
    read("warehouse.orders_daily")
    emit(READY_MARKER)

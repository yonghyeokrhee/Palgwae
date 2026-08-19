"""Fictional downstream service contract fixture."""

REQUIRED_DATASET = "warehouse.orders_daily"
REQUIRED_MARKER = "orders-daily-ready-v1"


def refresh_orders_api_cache():
    require(REQUIRED_MARKER)
    read(REQUIRED_DATASET)

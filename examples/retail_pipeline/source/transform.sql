INSERT INTO warehouse.orders_daily
SELECT
    order_date,
    COUNT(*) AS order_count,
    SUM(order_total) AS gross_revenue
FROM lake.orders_bronze
GROUP BY order_date;

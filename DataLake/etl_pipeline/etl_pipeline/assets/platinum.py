from dagster import AssetIn, asset
from pyspark.sql import DataFrame

from ..resources.spark_io_manager import get_spark_session, spark_output
from ..settings import spark_config_from_env


@asset(
    description="Sales cube: fact table joined with all dimensions for BI",
    ins={
        "dim_order": AssetIn(key_prefix=["gold", "dimorder"]),
        "dim_customer": AssetIn(key_prefix=["gold", "dimcustomer"]),
        "dim_seller": AssetIn(key_prefix=["gold", "dimseller"]),
        "dim_product": AssetIn(key_prefix=["gold", "dimproduct"]),
        "dim_date": AssetIn(key_prefix=["gold", "date"]),
        "fact_table": AssetIn(key_prefix=["gold", "facttable"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=["platinum", "sale"],
    compute_kind="PySpark",
    group_name="platinum",
    metadata={"merge_keys": ["order_id", "customer_unique_id"]},
)
def cube_sale(
    context,
    dim_order,
    dim_customer,
    dim_seller,
    dim_product,
    dim_date,
    fact_table: DataFrame,
):
    with get_spark_session(
        spark_config_from_env(), str(context.run.run_id).split("-")[0]
    ) as spark:
        spark.sql("CREATE SCHEMA IF NOT EXISTS platinum")

        data_mart = (
            fact_table.join(dim_order, on=["order_id"], how="inner")
            .join(dim_product, on="product_id", how="inner")
            .join(dim_customer, on="customer_id", how="inner")
            .join(dim_seller, on="seller_id", how="inner")
            .join(dim_date, on="dateKey", how="inner")
            .dropDuplicates(subset=["order_id", "customer_unique_id"])
        )

        return spark_output(data_mart, "cube_sale")

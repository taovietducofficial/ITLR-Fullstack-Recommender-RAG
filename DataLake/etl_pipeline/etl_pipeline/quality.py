from dagster import AssetCheckResult, AssetKey, asset_check
from pyspark.sql import functions as F

from .quality_rules import customer_dim_is_unique, fact_table_is_valid


@asset_check(
    asset=AssetKey(["gold", "facttable", "fact_table"]),
    description="Fact table has no null keys and no negative amounts",
)
def fact_table_valid(fact_table) -> AssetCheckResult:
    null_keys = fact_table.filter(
        F.col("order_id").isNull()
        | F.col("product_id").isNull()
        | F.col("customer_id").isNull()
    ).count()
    negative_amounts = fact_table.filter(
        (F.col("price") < 0) | (F.col("freight_value") < 0)
    ).count()
    return AssetCheckResult(
        passed=fact_table_is_valid(null_keys, negative_amounts),
        metadata={"null_keys": null_keys, "negative_amounts": negative_amounts},
    )


@asset_check(
    asset=AssetKey(["gold", "dimcustomer", "dim_customer"]),
    description="customer_id is unique and not null in the customer dimension",
)
def dim_customer_unique(dim_customer) -> AssetCheckResult:
    total = dim_customer.count()
    distinct = dim_customer.filter(F.col("customer_id").isNotNull()).select("customer_id").distinct().count()
    return AssetCheckResult(
        passed=customer_dim_is_unique(total, distinct),
        metadata={"rows": total, "duplicate_or_null": total - distinct},
    )

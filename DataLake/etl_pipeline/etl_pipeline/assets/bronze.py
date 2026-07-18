"""Bronze layer: raw MySQL tables extracted as-is into the lake.

One asset per source table, generated from BRONZE_TABLES. Asset names and
keys (bronze/<group>/<name>) match the tables the rest of the pipeline reads.
"""
import polars as pl
from dagster import Output, asset

COMPUTE_KIND = "SQL"
LAYER = "bronze"

# asset name -> (asset group, MySQL table)
BRONZE_TABLES = {
    "bronze_customer": ("customer", "customers"),
    "bronze_seller": ("seller", "sellers"),
    "bronze_product": ("product", "products"),
    "bronze_order": ("order", "orders"),
    "bronze_order_item": ("orderitem", "order_items"),
    "bronze_payment": ("payment", "payments"),
    "bronze_order_review": ("orderreview", "order_reviews"),
    "bronze_product_category": ("productcategory", "product_category_name_translation"),
    "bronze_geolocation": ("geolocation", "geolocation"),
}


def _bronze_asset(name: str, group: str, table: str):
    @asset(
        name=name,
        description=f"Extract MySQL table '{table}' into the Bronze layer",
        io_manager_key="minio_io_manager",
        required_resource_keys={"mysql_io_manager"},
        key_prefix=[LAYER, group],
        compute_kind=COMPUTE_KIND,
        group_name=LAYER,
    )
    def _asset(context) -> Output[pl.DataFrame]:
        df = context.resources.mysql_io_manager.extract_data(f"SELECT * FROM {table};")
        context.log.info(f"Extracted '{table}' with shape {df.shape}")
        return Output(
            value=df,
            metadata={
                "table": table,
                "row_count": df.shape[0],
                "column_count": df.shape[1],
                "columns": df.columns,
            },
        )

    return _asset


globals().update(
    {name: _bronze_asset(name, group, table) for name, (group, table) in BRONZE_TABLES.items()}
)

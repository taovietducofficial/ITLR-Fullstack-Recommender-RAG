import polars as pl
from dagster import AssetIn, AssetKey, asset
from pyspark.sql.functions import col
from pyspark.sql.functions import round as spark_round

from ..resources.spark_io_manager import get_spark_session, spark_output
from ..settings import spark_config_from_env

COMPUTE_KIND = "PySpark"
LAYER = "silver"

_BRAZIL_LAT_MAX = 5.27438888
_BRAZIL_LAT_MIN = -33.75116944
_BRAZIL_LNG_MIN = -73.98283055
_BRAZIL_LNG_MAX = -34.79314722


def _drop_nulls_and_duplicates(df):
    return df.na.drop().dropDuplicates()


def _clean_seller(df):
    return df.na.drop().dropDuplicates(subset=["seller_id"])


def _clean_product(df):
    df = _drop_nulls_and_duplicates(df)
    for column in (
        "product_description_length",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ):
        df = df.withColumn(column, col(column).cast("integer"))
    return df


def _clean_order_item(df):
    df = df.withColumn("price", spark_round(col("price"), 2).cast("double"))
    df = df.withColumn("freight_value", spark_round(col("freight_value"), 2).cast("double"))
    return _drop_nulls_and_duplicates(df)


def _clean_payment(df):
    df = df.withColumn("payment_value", spark_round(col("payment_value"), 2).cast("double"))
    df = df.withColumn("payment_installments", col("payment_installments").cast("integer"))
    return _drop_nulls_and_duplicates(df)


def _clean_order_review(df):
    return _drop_nulls_and_duplicates(df.drop("review_comment_title"))


def _clean_order(df):
    return df.na.drop().dropDuplicates(["order_id"])


def _clean_geolocation(df):
    df = _drop_nulls_and_duplicates(df)
    return df.filter(
        (col("geolocation_lat") <= _BRAZIL_LAT_MAX)
        & (col("geolocation_lat") >= _BRAZIL_LAT_MIN)
        & (col("geolocation_lng") >= _BRAZIL_LNG_MIN)
        & (col("geolocation_lng") <= _BRAZIL_LNG_MAX)
    )


SILVER_TABLES = {
    "silver_cleaned_customer": ("customer", "bronze_customer", "customer", _drop_nulls_and_duplicates),
    "silver_cleaned_seller": ("seller", "bronze_seller", "seller", _clean_seller),
    "silver_cleaned_product": ("product", "bronze_product", "product", _clean_product),
    "silver_cleaned_order_item": ("orderitem", "bronze_order_item", "orderitem", _clean_order_item),
    "silver_cleaned_payment": ("payment", "bronze_payment", "payment", _clean_payment),
    "silver_cleaned_order_review": ("orderreview", "bronze_order_review", "orderreview", _clean_order_review),
    "silver_cleaned_product_category": ("productcategory", "bronze_product_category", "productcategory", _drop_nulls_and_duplicates),
    "silver_cleaned_order": ("order", "bronze_order", "order", _clean_order),
    "silver_cleaned_geolocation": ("geolocation", "bronze_geolocation", "geolocation", _clean_geolocation),
}


def _silver_asset(name: str, group: str, src_name: str, src_group: str, transform):
    @asset(
        name=name,
        description=f"Clean bronze '{src_group}' into the Silver layer",
        ins={"upstream": AssetIn(key=AssetKey(["bronze", src_group, src_name]))},
        io_manager_key="spark_io_manager",
        key_prefix=[LAYER, group],
        compute_kind=COMPUTE_KIND,
        group_name=LAYER,
    )
    def _asset(context, upstream: pl.DataFrame):
        with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
            spark.sql("CREATE SCHEMA IF NOT EXISTS silver")
            spark_df = spark.createDataFrame(upstream.to_pandas())
            spark_df = transform(spark_df)
            return spark_output(spark_df, name)

    return _asset


globals().update(
    {
        name: _silver_asset(name, group, src_name, src_group, transform)
        for name, (group, src_name, src_group, transform) in SILVER_TABLES.items()
    }
)


@asset(
    description="Distinct order purchase timestamps, source for the date dimension",
    ins={"bronze_order": AssetIn(key_prefix=["bronze", "order"])},
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "date"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
)
def silver_date(context, bronze_order: pl.DataFrame):
    with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
        date_df = bronze_order.select("order_purchase_timestamp").to_pandas()
        date_df = spark.createDataFrame(date_df).na.drop().dropDuplicates()
        return spark_output(date_df, "silver_date")

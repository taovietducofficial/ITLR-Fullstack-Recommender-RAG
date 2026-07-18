from datetime import timedelta

from dagster import AssetIn, asset
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from ..resources.spark_io_manager import get_spark_session, spark_output
from ..settings import spark_config_from_env

COMPUTE_KIND = "PySpark"
LAYER = "gold"


@asset(
    description="Customer dimension: customers enriched with geolocation",
    ins={
        "silver_cleaned_customer": AssetIn(key_prefix=["silver", "customer"]),
        "silver_cleaned_geolocation": AssetIn(key_prefix=["silver", "geolocation"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "dimcustomer"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
    metadata={"merge_keys": ["customer_id"]},
)
def dim_customer(context, silver_cleaned_customer, silver_cleaned_geolocation: DataFrame):
    with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
        spark.sql("CREATE SCHEMA IF NOT EXISTS gold")

        joined_df = silver_cleaned_customer.join(
            silver_cleaned_geolocation,
            silver_cleaned_customer["customer_zip_code_prefix"]
            == silver_cleaned_geolocation["geolocation_zip_code_prefix"],
            how="left",
        )
        joined_df = (
            joined_df.withColumnRenamed("geolocation_lat", "customer_lat")
            .withColumnRenamed("geolocation_lng", "customer_lng")
            .withColumn("customer_city", joined_df["geolocation_city"])
            .withColumn("customer_state", joined_df["geolocation_state"])
            .drop(
                "geolocation_city",
                "geolocation_state",
                "customer_zip_code_prefix",
                "geolocation_zip_code_prefix",
            )
            .dropDuplicates(subset=["customer_id"])
        )

        final_df = joined_df.select(
            "customer_id",
            "customer_unique_id",
            "customer_city",
            "customer_state",
            "customer_lat",
            "customer_lng",
        )

        return spark_output(final_df, "dim_customer")


@asset(
    description="Seller dimension",
    ins={"silver_cleaned_seller": AssetIn(key_prefix=["silver", "seller"])},
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "dimseller"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
    metadata={"merge_keys": ["seller_id"]},
)
def dim_seller(context, silver_cleaned_seller: DataFrame):
    spark_df = silver_cleaned_seller.select("seller_id", "seller_zip_code_prefix")
    return spark_output(spark_df, "dim_seller")


@asset(
    description="Review dimension",
    ins={"silver_cleaned_order_review": AssetIn(key_prefix=["silver", "orderreview"])},
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "dimreview"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
    metadata={"merge_keys": ["review_id"]},
)
def dim_review(context, silver_cleaned_order_review: DataFrame):
    spark_df = silver_cleaned_order_review.select("review_id", "review_score")
    return spark_output(spark_df, "dim_review")


@asset(
    description="Product dimension with English category names",
    ins={
        "silver_cleaned_product": AssetIn(key_prefix=["silver", "product"]),
        "silver_cleaned_product_category": AssetIn(key_prefix=["silver", "productcategory"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "dimproduct"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
    metadata={"merge_keys": ["product_id"]},
)
def dim_product(context, silver_cleaned_product, silver_cleaned_product_category: DataFrame):
    spark_df = silver_cleaned_product.join(
        silver_cleaned_product_category, "product_category_name", "inner"
    ).select(
        "product_id",
        "product_category_name",
        "product_category_name_english",
        "product_name_length",
        "product_description_length",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    )

    return spark_output(spark_df, "dim_product")


@asset(
    description="Order dimension: order status and payment type",
    ins={
        "silver_cleaned_order": AssetIn(key_prefix=["silver", "order"]),
        "silver_cleaned_payment": AssetIn(key_prefix=["silver", "payment"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "dimorder"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
)
def dim_order(context, silver_cleaned_order, silver_cleaned_payment: DataFrame):
    df = silver_cleaned_order.join(silver_cleaned_payment, "order_id", "inner").select(
        "order_id", "order_status", "payment_type"
    )
    return spark_output(df, "dim_order")


@asset(
    description="Date dimension generated over the order purchase date range",
    ins={"silver_date": AssetIn(key_prefix=["silver", "date"])},
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, "date"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
)
def dim_date(context, silver_date: DataFrame):
    start_date = silver_date.select(F.min("order_purchase_timestamp")).first()[0]
    end_date = silver_date.select(F.max("order_purchase_timestamp")).first()[0]

    with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
        date_range = spark.sparkContext.parallelize(
            [(start_date + timedelta(days=x)) for x in range((end_date - start_date).days + 1)]
        )
        date_df = date_range.map(lambda x: (x,)).toDF(["date"])

    date_df = (
        date_df.withColumn(
            "dateKey",
            F.year(F.col("date")) * 10000
            + F.month(F.col("date")) * 100
            + F.dayofmonth(F.col("date")),
        )
        .withColumn("year", F.year(F.col("date")))
        .withColumn("quarter", F.quarter(F.col("date")))
        .withColumn("month", F.month(F.col("date")))
        .withColumn("week", F.weekofyear(F.col("date")))
        .withColumn("day", F.dayofmonth(F.col("date")))
        .withColumn("day_of_year", F.dayofyear(F.col("date")))
        .withColumn("day_name_of_week", F.date_format(F.col("date"), "EEEE"))
        .withColumn("month_name_of_week", F.date_format(F.col("date"), "MMMM"))
        .withColumnRenamed("date", "full_date")
        .selectExpr(
            "dateKey",
            "full_date",
            "year",
            "quarter",
            "month",
            "week",
            "day",
            "day_of_year",
            "day_name_of_week",
            "month_name_of_week",
        )
    )

    return spark_output(date_df, "dim_date")


@asset(
    description="Fact table of the star schema (SCD1)",
    io_manager_key="spark_io_manager",
    ins={
        "dim_customer": AssetIn(key_prefix=[LAYER, "dimcustomer"]),
        "dim_seller": AssetIn(key_prefix=[LAYER, "dimseller"]),
        "dim_product": AssetIn(key_prefix=[LAYER, "dimproduct"]),
        "dim_order": AssetIn(key_prefix=[LAYER, "dimorder"]),
        "silver_cleaned_order_item": AssetIn(key_prefix=["silver", "orderitem"]),
        "silver_cleaned_order": AssetIn(key_prefix=["silver", "order"]),
        "silver_cleaned_payment": AssetIn(key_prefix=["silver", "payment"]),
        "silver_cleaned_order_review": AssetIn(key_prefix=["silver", "orderreview"]),
        "silver_cleaned_product": AssetIn(key_prefix=["silver", "product"]),
        "dim_date": AssetIn(key_prefix=[LAYER, "date"]),
    },
    key_prefix=[LAYER, "facttable"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
)
def fact_table(
    context,
    dim_customer,
    dim_seller,
    dim_product,
    dim_order,
    silver_cleaned_order_item,
    silver_cleaned_order,
    silver_cleaned_payment,
    silver_cleaned_order_review,
    silver_cleaned_product,
    dim_date,
):
    orders = silver_cleaned_order.join(silver_cleaned_order_item, "order_id", "inner")
    fact = (
        orders.join(dim_order, on=["order_id"], how="inner")
        .join(dim_product, on="product_id", how="inner")
        .join(dim_customer, on="customer_id", how="inner")
        .join(dim_seller, on="seller_id", how="inner")
        .join(silver_cleaned_payment, on="order_id", how="inner")
        .join(silver_cleaned_order_review, on="order_id", how="inner")
        .join(
            dim_date,
            orders["order_purchase_timestamp"] == dim_date["full_date"],
            how="inner",
        )
        .select(
            "order_id",
            "order_item_id",
            "customer_id",
            "product_id",
            "review_id",
            "seller_id",
            "dateKey",
            "price",
            "freight_value",
            "payment_value",
            "payment_installments",
            "payment_sequential",
        )
    )
    return spark_output(fact, "fact_table")

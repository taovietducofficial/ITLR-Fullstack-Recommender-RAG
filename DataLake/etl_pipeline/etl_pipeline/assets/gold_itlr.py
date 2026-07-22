"""Gold layer, domain itlr: fact table tương tác, category denormalize thẳng (không có dim riêng)."""
import polars as pl
from dagster import AssetIn, asset
from pyspark.sql import DataFrame

from ..resources.spark_io_manager import get_spark_session, spark_output
from ..settings import spark_config_from_env

COMPUTE_KIND = "PySpark"
LAYER = "gold"
GROUP = "itlr"
GROUP_NAME = "itlr_gold"


@asset(
    name="gold_itlr_fact_interaction",
    description="Fact table: một dòng cho mỗi sự kiện tương tác user-course thật, kèm category",
    ins={
        "silver_itlr_interaction_events": AssetIn(key_prefix=["silver", "itlr"]),
        "bronze_itlr_course": AssetIn(key_prefix=["bronze", "itlr"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, GROUP],
    compute_kind=COMPUTE_KIND,
    group_name=GROUP_NAME,
    metadata={"merge_keys": ["user_id", "item_id", "event_type"]},
)
def gold_itlr_fact_interaction(
    context,
    silver_itlr_interaction_events: DataFrame,
    bronze_itlr_course: pl.DataFrame,
):
    with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
        spark.sql("CREATE SCHEMA IF NOT EXISTS gold")

        courses = spark.createDataFrame(bronze_itlr_course.to_pandas()).select(
            "item_id", "category"
        )
        fact = silver_itlr_interaction_events.join(courses, "item_id", "left").select(
            "user_id", "item_id", "category", "event_type", "event_time"
        )
        return spark_output(fact, "gold_itlr_fact_interaction")

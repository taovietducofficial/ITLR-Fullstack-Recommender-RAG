"""Silver layer, domain itlr: union enrollments + lesson_progress thành 1 bảng sự kiện tương tác."""
import polars as pl
from dagster import AssetIn, asset
from pyspark.sql import functions as F

from ..resources.spark_io_manager import get_spark_session, spark_output
from ..settings import spark_config_from_env

COMPUTE_KIND = "PySpark"
LAYER = "silver"
GROUP = "itlr"
GROUP_NAME = "itlr_silver"


@asset(
    name="silver_itlr_interaction_events",
    description="Union enrollments (in_progress/completed) + lesson_progress into one interaction-event table",
    ins={
        "bronze_itlr_enrollment": AssetIn(key_prefix=["bronze", "itlr"]),
        "bronze_itlr_lesson": AssetIn(key_prefix=["bronze", "itlr"]),
        "bronze_itlr_lesson_progress": AssetIn(key_prefix=["bronze", "itlr"]),
    },
    io_manager_key="spark_io_manager",
    key_prefix=[LAYER, GROUP],
    compute_kind=COMPUTE_KIND,
    group_name=GROUP_NAME,
)
def silver_itlr_interaction_events(
    context,
    bronze_itlr_enrollment: pl.DataFrame,
    bronze_itlr_lesson: pl.DataFrame,
    bronze_itlr_lesson_progress: pl.DataFrame,
):
    with get_spark_session(spark_config_from_env(), str(context.run.run_id).split("-")[0]) as spark:
        spark.sql("CREATE SCHEMA IF NOT EXISTS silver")

        enrollments = spark.createDataFrame(bronze_itlr_enrollment.to_pandas())
        enroll_events = (
            enrollments.na.drop(subset=["user_id", "course_id", "status"])
            # "saved" = bookmark, chưa phải tương tác thật
            .filter(F.col("status").isin("in_progress", "completed"))
            .select(
                F.col("user_id"),
                F.col("course_id").alias("item_id"),
                F.col("status").alias("event_type"),
                F.col("updated_at").alias("event_time"),
            )
        )

        lessons = spark.createDataFrame(bronze_itlr_lesson.to_pandas()).select(
            F.col("id").alias("lesson_id"), F.col("course_id")
        )
        progress = spark.createDataFrame(bronze_itlr_lesson_progress.to_pandas()).na.drop(
            subset=["user_id", "lesson_id", "completed_at"]
        )
        lesson_events = (
            progress.join(lessons, "lesson_id", "inner")
            .select(
                F.col("user_id"),
                F.col("course_id").alias("item_id"),
                F.lit("lesson_completed").alias("event_type"),
                F.col("completed_at").alias("event_time"),
            )
        )

        events = enroll_events.unionByName(lesson_events).dropDuplicates(
            ["user_id", "item_id", "event_type"]
        )
        return spark_output(events, "silver_itlr_interaction_events")

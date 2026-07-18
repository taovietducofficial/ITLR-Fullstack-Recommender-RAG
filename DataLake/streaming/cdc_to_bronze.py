"""Stream Debezium CDC events from Kafka into the Bronze layer as a Delta table.

Lands raw change events (one row per binlog event) into bronze.cdc_events,
keeping Bronze append-only. Parsing events into typed tables is downstream work.

Run on the Spark master:  make stream_cdc
"""
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")

spark = (
    SparkSession.builder.appName("cdc_to_bronze")
    .config(
        "spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.delta.catalog.DeltaCatalog",
    )
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
    .config("spark.hadoop.fs.s3a.endpoint", f"http://{MINIO_ENDPOINT}")
    .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY)
    .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY)
    .config("spark.hadoop.fs.s3a.path.style.access", "true")
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    .config(
        "spark.hadoop.fs.s3a.aws.credentials.provider",
        "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
    )
    .config("spark.sql.warehouse.dir", "s3a://lakehouse/")
    .config("hive.metastore.uris", "thrift://hive-metastore:9083")
    .config("spark.sql.catalogImplementation", "hive")
    .enableHiveSupport()
    .getOrCreate()
)

spark.sql("CREATE SCHEMA IF NOT EXISTS bronze")

events = (
    spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribePattern", "olist\\.olist\\..*")
    .option("startingOffsets", "earliest")
    .load()
)

parsed = events.select(
    F.col("topic"),
    F.regexp_extract("topic", r"([^.]+)$", 1).alias("table_name"),
    F.col("key").cast("string").alias("key"),
    F.col("value").cast("string").alias("value"),
    F.col("timestamp").alias("event_timestamp"),
)

query = (
    parsed.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "s3a://lakehouse/checkpoints/cdc_to_bronze")
    .toTable("bronze.cdc_events")
)

query.awaitTermination()

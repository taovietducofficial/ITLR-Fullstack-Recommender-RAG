"""Parse raw CDC events from bronze.cdc_events into typed per-table Delta tables.

Reads the raw event table as a stream and, per micro-batch, extracts the
Debezium `payload.after` document of each source table into an append-only
typed table bronze.cdc_<table> (schema inferred per batch, merged on drift).
Deletes (`after` is null) are skipped — Bronze stays append-only.

Run on the Spark master:  make stream_cdc_tables
"""
import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")

spark = (
    SparkSession.builder.appName("cdc_to_tables")
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


def process_batch(batch_df, batch_id):
    tables = [row.table_name for row in batch_df.select("table_name").distinct().collect()]
    for table in tables:
        raw = batch_df.filter(F.col("table_name") == table).select("value")
        parsed = spark.read.json(raw.rdd.map(lambda row: row.value))
        if "payload" not in parsed.columns:
            continue
        after = parsed.where("payload.after is not null").select("payload.after.*")
        if after.columns:
            (
                after.write.format("delta")
                .mode("append")
                .option("mergeSchema", "true")
                .saveAsTable(f"bronze.cdc_{table}")
            )


query = (
    spark.readStream.table("bronze.cdc_events")
    .writeStream.foreachBatch(process_batch)
    .option("checkpointLocation", "s3a://lakehouse/checkpoints/cdc_to_tables")
    .start()
)

query.awaitTermination()

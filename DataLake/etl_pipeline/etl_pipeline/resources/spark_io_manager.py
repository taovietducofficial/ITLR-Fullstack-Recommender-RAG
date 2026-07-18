from contextlib import contextmanager

from dagster import IOManager, InputContext, Output, OutputContext
from delta.tables import DeltaTable
from pyspark.sql import SparkSession, DataFrame

from ..utils.merge import build_merge_condition

_spark_session: SparkSession = None


def spark_output(df: DataFrame, table: str) -> Output:
    return Output(
        value=df,
        metadata={
            "table": table,
            "row_count": df.count(),
            "column_count": len(df.columns),
            "columns": df.columns,
        },
    )


@contextmanager
def get_spark_session(config, run_id="Spark IO Manager"):
    global _spark_session
    if _spark_session is None:
        _spark_session = (
            SparkSession.builder.master(config["spark_master"])
            .appName(run_id)
            .config(
                "spark.jars",
                "/usr/local/spark/jars/delta-core_2.12-2.2.0.jar,/usr/local/spark/jars/hadoop-aws-3.3.2.jar,/usr/local/spark/jars/delta-storage-2.2.0.jar,/usr/local/spark/jars/aws-java-sdk-1.12.367.jar,/usr/local/spark/jars/s3-2.18.41.jar,/usr/local/spark/jars/aws-java-sdk-bundle-1.11.1026.jar",
            )
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
            .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
            .config("spark.hadoop.fs.s3a.endpoint", f"http://{config['endpoint_url']}")
            .config("spark.hadoop.fs.s3a.access.key", str(config["minio_access_key"]))
            .config("spark.hadoop.fs.s3a.secret.key", str(config["minio_secret_key"]))
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.connection.ssl.enabled", "false")
            .config(
                "spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem"
            )
            .config('spark.hadoop.fs.s3a.aws.credentials.provider', 'org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider')
            .config('spark.sql.warehouse.dir', 's3a://lakehouse/')
            .config("hive.metastore.uris", "thrift://hive-metastore:9083")
            .config("spark.sql.catalogImplementation", "hive")
            .enableHiveSupport()
            .getOrCreate()
        )
    yield _spark_session


class SparkIOManager(IOManager):
    def __init__(self, config):
        self._config = config

    def handle_output(self, context: OutputContext, obj: DataFrame):
        layer, _, table = context.asset_key.path
        table_name = str(table.replace(f"{layer}_", ""))
        full_name = f"{layer}.{table_name}"
        merge_keys = (context.metadata or {}).get("merge_keys")
        spark = obj.sparkSession
        context.log.debug(f"(Spark handle_output) Writing {full_name} to MinIO ...")
        try:
            if merge_keys and spark.catalog.tableExists(full_name):
                condition = build_merge_condition(merge_keys)
                (
                    DeltaTable.forName(spark, full_name)
                    .alias("t")
                    .merge(obj.alias("s"), condition)
                    .whenMatchedUpdateAll()
                    .whenNotMatchedInsertAll()
                    .execute()
                )
            else:
                obj.write.format("delta").mode("overwrite").saveAsTable(full_name)
        except Exception:
            context.log.error(f"(Spark handle_output) Failed writing {full_name}")
            raise
        context.log.debug(f"Saved {table_name} to {layer}")

    def load_input(self, context: InputContext) -> DataFrame:
        layer, _, table = context.asset_key.path
        table_name = str(table.replace(f"{layer}_", ""))
        context.log.debug(f"Loading {layer}.{table_name} ...")
        try:
            with get_spark_session(self._config) as spark:
                df = spark.read.table(f"{layer}.{table_name}")
                context.log.debug(f"Loaded {df.count()} rows from {table_name}")
                return df
        except Exception:
            context.log.error(f"Failed loading {layer}.{table_name}")
            raise

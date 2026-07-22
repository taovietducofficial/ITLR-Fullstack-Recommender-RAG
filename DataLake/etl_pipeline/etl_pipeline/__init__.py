from dagster import Definitions, in_process_executor, load_assets_from_modules
from dagstermill import ConfigurableLocalOutputNotebookIOManager

from . import assets
from .quality import dim_customer_unique, fact_table_valid, itlr_fact_interaction_valid
from .job import reload_data, sync_itlr_interactions
from .schedule import reload_data_schedule, sync_itlr_interactions_schedule
from .resources.minio_io_manager import MinIOIOManager
from .resources.mysql_io_manager import MySQLIOManager
from .resources.postgres_io_manager import PostgresIOManager
from .resources.spark_io_manager import SparkIOManager
from .settings import (
    itlr_postgres_config_from_env,
    minio_config_from_env,
    mysql_config_from_env,
    spark_config_from_env,
)

resources = {
    "mysql_io_manager": MySQLIOManager(mysql_config_from_env()),
    "postgres_io_manager": PostgresIOManager(itlr_postgres_config_from_env()),
    "minio_io_manager": MinIOIOManager(minio_config_from_env()),
    "spark_io_manager": SparkIOManager(spark_config_from_env()),
    "output_notebook_io_manager": ConfigurableLocalOutputNotebookIOManager(),
}

defs = Definitions(
    assets=load_assets_from_modules([assets]),
    asset_checks=[fact_table_valid, dim_customer_unique, itlr_fact_interaction_valid],
    jobs=[reload_data, sync_itlr_interactions],
    schedules=[reload_data_schedule, sync_itlr_interactions_schedule],
    resources=resources,
    executor=in_process_executor,
)

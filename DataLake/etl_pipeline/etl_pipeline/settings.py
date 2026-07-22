import os
from typing import TypedDict


class MissingEnvVar(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"Required environment variable '{name}' is not set")
        self.name = name


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingEnvVar(name)
    return value


class MySQLConfig(TypedDict):
    host: str
    port: str
    database: str
    user: str
    password: str


class ITLRPostgresConfig(TypedDict):
    host: str
    port: str
    database: str
    user: str
    password: str


class MinIOConfig(TypedDict):
    endpoint_url: str
    minio_access_key: str
    minio_secret_key: str
    bucket: str


class SparkConfig(TypedDict):
    spark_master: str
    endpoint_url: str
    minio_access_key: str
    minio_secret_key: str


def mysql_config_from_env() -> MySQLConfig:
    return {
        "host": _require("MYSQL_HOST"),
        "port": _require("MYSQL_PORT"),
        "database": _require("MYSQL_DATABASES"),
        "user": _require("MYSQL_ROOT_USER"),
        "password": _require("MYSQL_ROOT_PASSWORD"),
    }


def itlr_postgres_config_from_env() -> ITLRPostgresConfig:
    # ITLR_PG_* riêng, không trùng POSTGRES_* (đó là Postgres nội bộ của Dagster, de_psql)
    return {
        "host": _require("ITLR_PG_HOST"),
        "port": _require("ITLR_PG_PORT"),
        "database": _require("ITLR_PG_DATABASE"),
        "user": _require("ITLR_PG_USER"),
        "password": _require("ITLR_PG_PASSWORD"),
    }


def minio_config_from_env() -> MinIOConfig:
    return {
        "endpoint_url": _require("MINIO_ENDPOINT"),
        "minio_access_key": _require("MINIO_ACCESS_KEY"),
        "minio_secret_key": _require("MINIO_SECRET_KEY"),
        "bucket": _require("DATALAKE_BUCKET"),
    }


def spark_config_from_env() -> SparkConfig:
    minio = minio_config_from_env()
    return {
        "spark_master": os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077"),
        "endpoint_url": minio["endpoint_url"],
        "minio_access_key": minio["minio_access_key"],
        "minio_secret_key": minio["minio_secret_key"],
    }

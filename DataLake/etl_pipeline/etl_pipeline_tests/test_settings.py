import importlib.util
import os
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "settings", Path(__file__).resolve().parent.parent / "etl_pipeline" / "settings.py"
)
_settings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_settings)

MYSQL_VARS = ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASES", "MYSQL_ROOT_USER", "MYSQL_ROOT_PASSWORD"]
MINIO_VARS = ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "DATALAKE_BUCKET"]
ITLR_PG_VARS = ["ITLR_PG_HOST", "ITLR_PG_PORT", "ITLR_PG_DATABASE", "ITLR_PG_USER", "ITLR_PG_PASSWORD"]


@pytest.fixture
def clean_env(monkeypatch):
    for name in MYSQL_VARS + MINIO_VARS + ITLR_PG_VARS + ["SPARK_MASTER_URL"]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_mysql_config_raises_when_missing(clean_env):
    with pytest.raises(_settings.MissingEnvVar):
        _settings.mysql_config_from_env()


def test_mysql_config_builds_when_present(clean_env):
    for name, value in zip(MYSQL_VARS, ["mysql", "3306", "olist", "root", "admin"]):
        clean_env.setenv(name, value)
    config = _settings.mysql_config_from_env()
    assert config == {
        "host": "mysql",
        "port": "3306",
        "database": "olist",
        "user": "root",
        "password": "admin",
    }


def test_minio_config_raises_when_missing(clean_env):
    with pytest.raises(_settings.MissingEnvVar):
        _settings.minio_config_from_env()


def test_itlr_postgres_config_raises_when_missing(clean_env):
    with pytest.raises(_settings.MissingEnvVar):
        _settings.itlr_postgres_config_from_env()


def test_itlr_postgres_config_builds_when_present(clean_env):
    for name, value in zip(ITLR_PG_VARS, ["host.docker.internal", "5433", "it_learning", "postgres", "postgres"]):
        clean_env.setenv(name, value)
    config = _settings.itlr_postgres_config_from_env()
    assert config == {
        "host": "host.docker.internal",
        "port": "5433",
        "database": "it_learning",
        "user": "postgres",
        "password": "postgres",
    }


def test_spark_config_defaults_master_when_unset(clean_env):
    for name, value in zip(MINIO_VARS, ["minio:9000", "minio", "minio123", "lakehouse"]):
        clean_env.setenv(name, value)
    config = _settings.spark_config_from_env()
    assert config["spark_master"] == "spark://spark-master:7077"
    assert config["endpoint_url"] == "minio:9000"


def test_spark_config_honors_explicit_master(clean_env):
    for name, value in zip(MINIO_VARS, ["minio:9000", "minio", "minio123", "lakehouse"]):
        clean_env.setenv(name, value)
    clean_env.setenv("SPARK_MASTER_URL", "spark://custom:7077")
    assert _settings.spark_config_from_env()["spark_master"] == "spark://custom:7077"

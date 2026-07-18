import os
import tempfile
import uuid
from contextlib import contextmanager
from typing import Union

import polars as pl
import urllib3.exceptions
from dagster import IOManager, InputContext, OutputContext
from minio import Minio
from minio.error import ServerError

from ..utils.retry import retry

MINIO_RETRY_EXCEPTIONS = (urllib3.exceptions.HTTPError, ServerError)


@contextmanager
def connect_minio(config):
    client = Minio(
        endpoint=config.get("endpoint_url"),
        access_key=config.get("minio_access_key"),
        secret_key=config.get("minio_secret_key"),
        secure=False,
    )
    yield client


@retry(times=3, delay_seconds=2, exceptions=MINIO_RETRY_EXCEPTIONS)
def make_bucket(client: Minio, bucket_name, log):
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
    else:
        log.debug(f"Bucket {bucket_name} already exists")


@retry(times=3, delay_seconds=2, exceptions=MINIO_RETRY_EXCEPTIONS)
def _upload(client: Minio, bucket_name, key_name, file_path):
    client.fput_object(bucket_name, key_name, file_path)


@retry(times=3, delay_seconds=2, exceptions=MINIO_RETRY_EXCEPTIONS)
def _download(client: Minio, bucket_name, key_name, file_path):
    client.fget_object(bucket_name, key_name, file_path)


class MinIOIOManager(IOManager):
    def __init__(self, config):
        self._config = config

    def _get_path(self, context: Union[InputContext, OutputContext]):
        layer, schema, table = context.asset_key.path
        key = "/".join([layer, schema, table.replace(f"{layer}_", "")])
        tmp_file_path = os.path.join(
            tempfile.gettempdir(), f"{'_'.join(context.asset_key.path)}_{uuid.uuid4().hex}.parquet"
        )

        if context.has_partition_key:
            partition_str = str(table) + "_" + context.asset_partition_key
            return os.path.join(key, f"{partition_str}.parquet"), tmp_file_path
        return f"{key}.parquet", tmp_file_path

    def handle_output(self, context: OutputContext, obj: pl.DataFrame):
        key_name, tmp_file_path = self._get_path(context)
        obj.write_parquet(tmp_file_path)
        try:
            bucket_name = self._config.get("bucket")
            with connect_minio(self._config) as client:
                make_bucket(client, bucket_name, context.log)
                _upload(client, bucket_name, key_name, tmp_file_path)
                context.log.info(f"(MinIO handle_output) Number of rows and columns: {obj.shape}")
                context.add_output_metadata({"path": key_name, "tmp": tmp_file_path})
        finally:
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)

    def load_input(self, context: InputContext):
        bucket_name = self._config.get("bucket")
        key_name, tmp_file_path = self._get_path(context)
        try:
            with connect_minio(self._config) as client:
                make_bucket(client, bucket_name, context.log)
                context.log.info(f"(MinIO load_input) from key_name: {key_name}")
                _download(client, bucket_name, key_name, tmp_file_path)
                df_data = pl.read_parquet(tmp_file_path)
                context.log.info(f"(MinIO load_input) Got polars dataframe with shape: {df_data.shape}")
                return df_data
        finally:
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)

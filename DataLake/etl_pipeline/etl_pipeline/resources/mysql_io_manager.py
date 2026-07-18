from dagster import IOManager, InputContext, OutputContext
import polars as pl


def connect_mysql(config) -> str:
    conn_info = (
        f"mysql://{config['user']}:{config['password']}"
        + f"@{config['host']}:{config['port']}"
        + f"/{config['database']}"
    )
    return conn_info


class MySQLIOManager(IOManager):
    def __init__(self, config):
        self._config = config

    def handle_output(self, context: OutputContext, obj: pl.DataFrame):
        raise NotImplementedError("MySQLIOManager is extract-only; use extract_data() instead")

    def load_input(self, context: InputContext):
        raise NotImplementedError("MySQLIOManager is extract-only; use extract_data() instead")

    def extract_data(self, sql: str) -> pl.DataFrame:
        conn_info = connect_mysql(self._config)
        return pl.read_database(query=sql, connection_uri=conn_info)
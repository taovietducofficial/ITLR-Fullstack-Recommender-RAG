import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "job", Path(__file__).resolve().parent.parent / "etl_pipeline" / "job" / "__init__.py"
)
_job = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_job)


def test_reload_data_job_name():
    assert _job.reload_data.name == "reload_data"


def test_reload_data_selects_only_bronze_group():
    from dagster import AssetKey, asset

    @asset(group_name="bronze")
    def bronze_customer():
        return 1

    @asset(group_name="silver")
    def silver_cleaned_customer():
        return 1

    selected = _job.bronze_data_by_week.resolve([bronze_customer, silver_cleaned_customer])
    assert selected == {AssetKey("bronze_customer")}

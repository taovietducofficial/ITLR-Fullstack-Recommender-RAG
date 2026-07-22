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


def test_reload_data_ignores_itlr_bronze_group():
    """Thêm domain itlr (group_name khác) không được làm reload_data (Olist) chọn nhầm asset."""
    from dagster import AssetKey, asset

    @asset(group_name="bronze")
    def bronze_customer():
        return 1

    @asset(group_name="itlr_bronze")
    def bronze_itlr_course():
        return 1

    selected = _job.bronze_data_by_week.resolve([bronze_customer, bronze_itlr_course])
    assert selected == {AssetKey("bronze_customer")}


def test_sync_itlr_interactions_job_name():
    assert _job.sync_itlr_interactions.name == "sync_itlr_interactions"


def test_itlr_pipeline_selects_only_itlr_groups():
    from dagster import AssetKey, asset

    @asset(group_name="bronze")
    def bronze_customer():
        return 1

    @asset(group_name="itlr_bronze")
    def bronze_itlr_course():
        return 1

    @asset(group_name="itlr_silver")
    def silver_itlr_interaction_events():
        return 1

    @asset(group_name="itlr_gold")
    def gold_itlr_fact_interaction():
        return 1

    selected = _job.itlr_pipeline.resolve(
        [bronze_customer, bronze_itlr_course, silver_itlr_interaction_events, gold_itlr_fact_interaction]
    )
    assert selected == {
        AssetKey("bronze_itlr_course"),
        AssetKey("silver_itlr_interaction_events"),
        AssetKey("gold_itlr_fact_interaction"),
    }

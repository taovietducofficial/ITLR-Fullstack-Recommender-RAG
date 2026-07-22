from dagster import AssetSelection, define_asset_job

BRONZE = "bronze"
ITLR_GROUPS = ["itlr_bronze", "itlr_silver", "itlr_gold"]

bronze_data_by_week = AssetSelection.groups(BRONZE)
itlr_pipeline = AssetSelection.groups(*ITLR_GROUPS)

reload_data = define_asset_job(
    name="reload_data",
    selection=bronze_data_by_week,
)

sync_itlr_interactions = define_asset_job(
    name="sync_itlr_interactions",
    selection=itlr_pipeline,
)


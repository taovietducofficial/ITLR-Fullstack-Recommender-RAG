from dagster import AssetSelection, define_asset_job

BRONZE = "bronze"

bronze_data_by_week = AssetSelection.groups(BRONZE)

reload_data = define_asset_job(
    name="reload_data",
    selection=bronze_data_by_week,
)


from dagster import ScheduleDefinition

from ..job import reload_data, sync_itlr_interactions

reload_data_schedule = ScheduleDefinition(
    job=reload_data,
    cron_schedule="30 21 06 04 *",
)

# Trước giờ chạy scripts/sync_interactions.ps1 (03:30)
sync_itlr_interactions_schedule = ScheduleDefinition(
    job=sync_itlr_interactions,
    cron_schedule="0 3 * * *",
)

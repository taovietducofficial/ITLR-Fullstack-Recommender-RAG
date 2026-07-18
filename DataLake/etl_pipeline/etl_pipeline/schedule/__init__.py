from dagster import ScheduleDefinition

from ..job import reload_data

reload_data_schedule = ScheduleDefinition(
    job=reload_data,
    cron_schedule="30 21 06 04 *",
)

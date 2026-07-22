"""Bronze layer, domain itlr: raw Postgres tables from web/ (the recommender's app DB)."""
from .bronze import _bronze_asset

GROUP = "itlr"
GROUP_NAME = "itlr_bronze"  # tách khỏi group "bronze" -> reload_data (Olist) không đụng vào

ITLR_TABLES = {
    "bronze_itlr_course": "courses",
    "bronze_itlr_enrollment": "enrollments",
    "bronze_itlr_lesson": "lessons",
    "bronze_itlr_lesson_progress": "lesson_progress",
    # users: chứa email (PII), không có downstream nào cần gì ngoài user_id -> bỏ qua
}

globals().update({
    name: _bronze_asset(name, GROUP, table, resource_key="postgres_io_manager", group_name=GROUP_NAME)
    for name, table in ITLR_TABLES.items()
})

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "quality_rules", Path(__file__).resolve().parent.parent / "etl_pipeline" / "quality_rules.py"
)
_quality_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_quality_rules)
fact_table_is_valid = _quality_rules.fact_table_is_valid
customer_dim_is_unique = _quality_rules.customer_dim_is_unique


def test_fact_table_valid_when_clean():
    assert fact_table_is_valid(null_keys=0, negative_amounts=0) is True


def test_fact_table_invalid_with_null_keys():
    assert fact_table_is_valid(null_keys=1, negative_amounts=0) is False


def test_fact_table_invalid_with_negative_amounts():
    assert fact_table_is_valid(null_keys=0, negative_amounts=1) is False


def test_customer_dim_unique_when_no_duplicates():
    assert customer_dim_is_unique(total_rows=100, distinct_rows=100) is True


def test_customer_dim_not_unique_with_duplicates():
    assert customer_dim_is_unique(total_rows=100, distinct_rows=98) is False

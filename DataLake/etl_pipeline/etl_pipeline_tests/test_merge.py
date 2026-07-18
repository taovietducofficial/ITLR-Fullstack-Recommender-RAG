import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "merge", Path(__file__).resolve().parent.parent / "etl_pipeline" / "utils" / "merge.py"
)
_merge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_merge)
build_merge_condition = _merge.build_merge_condition


def test_single_key():
    assert build_merge_condition(["customer_id"]) == "t.customer_id = s.customer_id"


def test_composite_key():
    assert (
        build_merge_condition(["order_id", "customer_unique_id"])
        == "t.order_id = s.order_id AND t.customer_unique_id = s.customer_unique_id"
    )

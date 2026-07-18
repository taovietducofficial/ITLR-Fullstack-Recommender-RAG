import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "retry", Path(__file__).resolve().parent.parent / "etl_pipeline" / "utils" / "retry.py"
)
_retry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_retry)
retry = _retry.retry


def test_returns_result_on_first_success():
    calls = []

    @retry(times=3, delay_seconds=0)
    def fn():
        calls.append(1)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 1


def test_retries_until_success():
    calls = []

    @retry(times=3, delay_seconds=0)
    def fn():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("transient")
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 2


def test_raises_after_exhausting_attempts():
    calls = []

    @retry(times=3, delay_seconds=0)
    def fn():
        calls.append(1)
        raise ValueError("permanent")

    try:
        fn()
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert len(calls) == 3


def test_only_catches_declared_exceptions():
    @retry(times=3, delay_seconds=0, exceptions=(ValueError,))
    def fn():
        raise TypeError("not covered")

    try:
        fn()
        assert False, "expected TypeError"
    except TypeError:
        pass

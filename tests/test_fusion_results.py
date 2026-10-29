import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/export_fusion_results.py"
SPEC = importlib.util.spec_from_file_location("export_fusion_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_pair_aggregation_uses_ratio_of_sums_not_mean_percentages():
    rows = [{"s1": 50, "mp": 100}, {"s1": 100, "mp": 100}]
    result = MODULE.aggregate_pairs(rows, "s1", "mp")
    assert result["improvement_percent"] == pytest.approx(25.0)
    assert result["wins"] == 1


def test_representative_is_closest_to_group_improvement():
    rows = [
        {"case_id": "a", "improvement_percent": 3.0},
        {"case_id": "b", "improvement_percent": 9.5},
        {"case_id": "c", "improvement_percent": 20.0},
    ]
    assert MODULE.select_representative(rows, 10.0)["case_id"] == "b"


def test_latency_excludes_interlock_and_separates_first_call():
    run = {"dec_log": [[5.1, "extend", 1400, "model"], [10.1, "extend", 0, "interlock"], [15.1, "extend", 480, "model"]]}
    calls = MODULE.extract_model_calls(run)
    assert calls == [1400.0, 480.0]
    summary = MODULE.latency_summary([calls, [1200.0, 500.0]])
    assert summary["first_call_per_run"]["count"] == 2
    assert summary["first_call_per_run"]["mean_ms"] == 1300.0
    assert summary["subsequent_calls"]["mean_ms"] == 490.0
    assert summary["all_calls"]["under_1s_fraction"] == 0.5

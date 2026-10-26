import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def metrics_module():
    path = Path(__file__).resolve().parents[1] / "reproduction/protocol/intersection_metrics.py"
    spec = importlib.util.spec_from_file_location("intersection_metrics_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_queue_counts_unique_incoming_lanes_and_excludes_warmup(metrics_module):
    counts = {"in_0": 2, "in_1": 1, ":crossing": 50}
    connection = SimpleNamespace(
        trafficlight=SimpleNamespace(
            getControlledLanes=lambda tls: ("in_0", "in_0", "in_1", ":crossing"),
            getRedYellowGreenState=lambda tls: "Gr" if counts["in_0"] else "yr"),
        lane=SimpleNamespace(getLastStepHaltingNumber=lambda lane: counts[lane]))
    metrics = metrics_module.IntersectionMetrics(connection, "1", start=10.0, end=12.0)
    for now in (9.0, 10.0, 11.0):
        metrics.update(now)
    counts["in_0"] = 0
    metrics.update(12.0)
    metrics.update(13.0)
    assert metrics.observed_seconds == 2.0
    assert sum(metrics.queue_vehicle_seconds.values()) == 4.0
    assert metrics.max_queue_vehicles == 3
    assert metrics.signal_timeline == [{'time_s': 9.0, 'state': 'Gr'}, {'time_s': 12.0, 'state': 'yr'}]


def test_waiting_uses_formal_vehicles_including_unfinished(metrics_module, tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text('<tripinfos>'
                    '<tripinfo id="warm" depart="0" arrival="9" waitingTime="900" waitingCount="99" timeLoss="999"/>'
                    '<tripinfo id="a" depart="12" arrival="20" waitingTime="2" waitingCount="1" timeLoss="3"/>'
                    '<tripinfo id="b" depart="13" arrival="-1" waitingTime="6" waitingCount="2" timeLoss="8"/>'
                    '</tripinfos>')
    report = metrics_module.trip_metrics(path, {"a": 10, "b": 12}, 30)
    assert report["mean_stopped_time_s"] == 4.0
    assert report["mean_stop_count"] == 1.5
    assert report["mean_time_loss_s"] == 5.5
    assert report["mean_insertion_wait_s"] == 1.5
    assert report["arrived_vehicles"] == 1
    assert report["unfinished_inserted_vehicles"] == 1
    assert not report["all_formal_journeys_complete"]


def test_never_inserted_vehicle_does_not_become_zero_wait(metrics_module, tmp_path):
    path = tmp_path / "tripinfo.xml"
    path.write_text('<tripinfos><tripinfo id="a" depart="12" arrival="20" '
                    'waitingTime="2" waitingCount="1" timeLoss="3"/></tripinfos>')
    report = metrics_module.trip_metrics(path, {"a": 10, "b": 12, "future": 40}, 30)
    assert report["planned_vehicles"] == 2
    assert report["not_inserted_vehicles"] == 1
    assert report["mean_stopped_time_s"] is None
    assert report["mean_stop_count"] is None
    assert report["mean_insertion_wait_s"] == 10.0

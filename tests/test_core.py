import copy
from pathlib import Path

import pytest

from deepsignal_s1.control import SignalController
from deepsignal_s1.data import build_plan, load_scene, signal_links
from deepsignal_s1.metrics import TripMetrics


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scene():
    return load_scene(ROOT / "scenarios/nansha-j02/scene.json")


def test_same_seed_produces_same_arrivals(scene):
    assert build_plan(scene, "east-west", 99001) == build_plan(
        scene, "east-west", 99001
    )
    assert build_plan(scene, "east-west", 99001) != build_plan(
        scene, "east-west", 99002
    )


@pytest.mark.parametrize("regime", ["east-west", "north-south", "time-varying"])
def test_arrivals_cover_valid_routes(scene, regime):
    plan = build_plan(scene, regime, 99001)
    assert set(v["approach"] for v in plan["vehicles"]) == set("EWNS")
    assert any(v["cohort"] == "warmup" for v in plan["vehicles"])
    assert any(v["cohort"] == "formal" for v in plan["vehicles"])
    assert all(v["route_edges"] for v in plan["vehicles"])


def test_invalid_duration_rejected(scene):
    with pytest.raises(ValueError):
        build_plan(scene, "east-west", 1, duration=0)


def test_scene_signal_movements(scene):
    links, width = signal_links(scene)
    assert width == 19
    assert all(links.values())
    assert len(set(i for values in links.values() for i in values)) == sum(
        map(len, links.values())
    )


def test_town_signal_movements():
    scene = load_scene(ROOT / "scenarios/town10hd/scene.json")
    links, width = signal_links(scene)
    assert width >= 20
    assert all(links.values())


def test_green_extension_and_transition_timing(scene):
    control = SignalController(scene)
    control.advance(0.2)
    assert not control.advance(5.1)
    assert control.advance(5.2)
    control.accept("extend_5s")
    assert control.green_total == 15
    assert control.next_time == pytest.approx(10.2)
    assert control.advance(10.2)
    control.accept("switch_to_n2")
    assert control.snapshot(10.2)["countdown_s"] == pytest.approx(5)
    control.advance(15.2)
    assert control.stage == "yellow"
    control.advance(18.2)
    assert control.stage == "red"
    control.advance(29.2)
    assert control.stage == "green" and control.phase == "n2"


def test_cannot_extend_past_max_green(scene):
    control = SignalController(scene)
    control.advance(0.2)
    for _ in range(10):
        assert control.advance(control.next_time)
        control.accept("extend_5s")
    assert control.green_total == 60
    control.advance(control.next_time)
    assert "extend_5s" not in control.legal_actions(control.decision_at)


def test_illegal_action_not_replaced(scene):
    control = SignalController(scene)
    control.advance(0.2)
    control.advance(5.2)
    with pytest.raises(ValueError):
        control.accept("switch_to_unknown")
    assert control.waiting


def test_fixed_uses_tuned_table_not_inherited_greens(scene):
    control = SignalController(scene, fixed=True)
    control.advance(0.2)
    assert control.green_total == 14
    control.advance(14.2)
    control.advance(17.2)
    control.advance(28.2)
    assert control.phase == "n2" and control.green_total == 13


def test_journey_includes_entry_wait_and_no_completed_only_bias():
    plan = {
        "window": [0, 10],
        "vehicles": [
            {"vehicle_id": "a", "planned_depart": 1, "cohort": "formal"},
            {"vehicle_id": "b", "planned_depart": 2, "cohort": "formal"},
        ],
    }
    metrics = TripMetrics(plan)
    metrics.update(11, ["a"], 0, 0.1)
    assert metrics.report(11)["mean_journey_s"] is None
    assert metrics.report(11)["unfinished"] == 1
    metrics.update(22, ["b"], 0, 0.1)
    assert metrics.report(22)["mean_journey_s"] == 15


def test_model_context_contains_no_traffic_ground_truth(scene):
    control = SignalController(scene)
    control.advance(0.2)
    control.advance(5.2)
    context = control.context(5.2)
    assert set(context) == {"intersection", "signal", "legal_actions"}
    assert set(context["signal"]) == {
        "current_phase",
        "green_elapsed_s",
        "committed_total_green_s",
    }


def test_scene_load_does_not_modify_config(scene):
    before = copy.deepcopy(scene)
    build_plan(scene, "east-west", 99001)
    assert before == scene

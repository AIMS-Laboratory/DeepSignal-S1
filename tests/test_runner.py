"""Exercise the real SUMO loop with an explicitly simulated model transport."""

import shutil
from pathlib import Path

import pytest

from deepsignal_s1.data import build_plan, load_scene, read_json


pytestmark = pytest.mark.skipif(
    shutil.which("sumo") is None, reason="SUMO executable required"
)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_camera(monkeypatch):
    import deepsignal_s1.scene as module

    class Scene:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def capture(self, *args):
            return b"camera-test-double"

        def encode_model_input(self, image):
            return image

    monkeypatch.setattr(module, "CameraScene", Scene)


def test_online_loop_samples_and_completes_without_ground_truth_transport(
    tmp_path, monkeypatch, fake_camera
):
    import deepsignal_s1.runner as runner

    requests = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def decide(self, context, frames):
            requests.append(context)
            assert len(frames) == 3
            assert set(context) == {"intersection", "signal", "legal_actions"}
            order = [p["key"] for p in context["intersection"]["phases"]]
            current = context["signal"]["current_phase"]
            next_action = "switch_to_" + order[(order.index(current) + 1) % len(order)]
            action = (
                next_action
                if next_action in context["legal_actions"]
                else context["legal_actions"][0]
            )
            return {"choice": action, "model_version": "explicit-unit-test-double"}

    monkeypatch.setattr(runner, "ModelClient", Client)
    scene = load_scene(ROOT / "scenarios/nansha-j02/scene.json")
    plan = build_plan(scene, "east-west", 99001, duration=30)
    result = runner.run_episode(
        scene, plan, tmp_path / "run", controller="s1", endpoint="test-double"
    )
    assert result["complete"] and requests
    assert result["metrics"]["completed"] == result["metrics"]["vehicles"]
    assert not result["realtime_verified"]
    assert (
        read_json(tmp_path / "run/report.json")["model_version"]
        == "explicit-unit-test-double"
    )


def test_failures_are_retained_and_not_replaced(tmp_path, monkeypatch, fake_camera):
    import deepsignal_s1.runner as runner

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def decide(self, *args):
            raise RuntimeError("explicit test transport failure")

    monkeypatch.setattr(runner, "ModelClient", Client)
    scene = load_scene(ROOT / "scenarios/nansha-j02/scene.json")
    plan = build_plan(scene, "east-west", 99001, duration=30)
    with pytest.raises(RuntimeError, match="test transport failure"):
        runner.run_episode(
            scene, plan, tmp_path / "run", controller="s1", endpoint="test-double"
        )
    report = read_json(tmp_path / "run/report.json")
    assert not report["complete"]
    assert report["metrics"]["mean_journey_s"] is None
    assert (tmp_path / "run/plan.json").exists()

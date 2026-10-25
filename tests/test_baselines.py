import io
import json
from pathlib import Path

from deepsignal_s1.baselines import VisualPressureClient
from deepsignal_s1.data import load_scene


def test_yolo_mp_ties_prioritize_longest_red_then_phase_order(monkeypatch):
    scene = load_scene(
        Path(__file__).resolve().parents[1] / "scenarios/nansha-j02/scene.json"
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps({"movement_calib": {}}).encode()),
    )
    baseline = VisualPressureClient("http://test-double", scene, {})
    context = {
        "signal": {"current_phase": "n1", "red_age_s": {
            "n1": 0, "n2": 20, "n3": 50, "n4": 50,
        }},
        "legal_actions": ["switch_to_n2", "switch_to_n3", "switch_to_n4"],
    }
    result = baseline.decide(context, [b"a", b"b", b"c"])
    assert result == {"choice": "switch_to_n3", "model_version": "yolo-mp-v1"}
    context["legal_actions"].insert(0, "extend_5s")
    assert baseline.decide(context, [b"a", b"b", b"c"])["choice"] == "extend_5s"

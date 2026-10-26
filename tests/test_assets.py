import json

import pytest

from deepsignal_s1 import assets


@pytest.mark.parametrize("scene,subdir", [("nansha-j02", "nansha"), ("town10hd", "town10hd")])
def test_combined_package_selects_matching_runtime(tmp_path, monkeypatch, scene, subdir):
    runtime = tmp_path / "runtime" / subdir / "Linux"
    binary = runtime / "CarlaUnreal/Binaries/Linux/CarlaUnreal-Linux-Shipping"
    binary.parent.mkdir(parents=True)
    binary.touch()
    (tmp_path / "scene_package.json").write_text(json.dumps({
        "scenes": ["nansha-j02", "town10hd"],
        "runtimes": {"nansha-j02": "runtime/nansha/Linux", "town10hd": "runtime/town10hd/Linux"},
    }))
    calls = []
    monkeypatch.setattr(assets.subprocess, "call", lambda command, **kw: calls.append((command, kw)) or 0)
    assert assets.launch(tmp_path, {"id": scene}, port=25100, adapter=1) == 0
    command, options = calls[0]
    assert command[0] == str(binary)
    assert options["cwd"] == runtime
    assert "-carla-streaming-port=25101" in command
    assert "-graphicsadapter=1" in command
    assert "-quality-level=Epic" in command


def test_scene_not_in_combined_package(tmp_path):
    (tmp_path / "scene_package.json").write_text('{"scenes": ["town10hd"]}')
    with pytest.raises(ValueError, match="does not contain"):
        assets.launch(tmp_path, {"id": "nansha-j02"})

"""Install the separately distributed simulation scene package."""

import json
import os
from pathlib import Path
import subprocess
import tarfile


def install(archive, target):
    archive, target = Path(archive), Path(target)
    if target.exists() and any(target.iterdir()):
        raise ValueError("The asset destination must be empty")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as package:
        package.extractall(target, filter="data")
    manifest = target / "scene_package.json"
    if not manifest.exists():
        raise ValueError(
            "Not a DeepSignal-S1 scene package: scene_package.json is missing"
        )
    value = json.loads(manifest.read_text())
    if value["carla_version"] != "0.10.0":
        raise ValueError(
            "This release requires the matching CARLA 0.10.0 scene package"
        )
    return value


def launch(directory, scene, *, port=25020, adapter=0):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "scene_package.json").read_text())
    if scene["id"] not in manifest["scenes"]:
        raise ValueError(
            "This asset package does not contain the requested scene; use its matching runtime"
        )
    runtime = directory / manifest["runtimes"][scene["id"]]
    binary = runtime / "CarlaUnreal/Binaries/Linux/CarlaUnreal-Linux-Shipping"
    if not binary.exists():
        raise ValueError("Install the scene runtime package first")
    if not os.access(binary, os.X_OK):
        binary.chmod(binary.stat().st_mode | 0o100)
    command = [
        str(binary),
        "CarlaUnreal",
        f"-carla-rpc-port={port}",
        f"-carla-streaming-port={port + 1}",
        f"-graphicsadapter={adapter}",
        "-quality-level=Epic",
        "-RenderOffScreen",
        "-nosound",
    ]
    return subprocess.call(command, cwd=runtime)

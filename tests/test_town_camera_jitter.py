import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("filename", ["town_s1.py", "town_pressure.py"])
@pytest.mark.parametrize("amplitude", [0, 8])
def test_town_jitter_does_not_read_unpublished_spawn_pose(filename, amplitude):
    root = Path(__file__).resolve().parents[1] / "reproduction"

    world = SimpleNamespace(ticks=0)
    def tick():
        world.ticks += 1
    world.tick = tick

    class Camera:
        def __init__(self):
            self.pose = SimpleNamespace(location=(50.0, 80.0, 10.0),
                                        rotation=SimpleNamespace(yaw=90.0, pitch=-35.8, roll=0.0))

        def get_transform(self):
            if world.ticks:
                return deepcopy(self.pose)
            return SimpleNamespace(location=(0.0, 0.0, 0.0),
                                   rotation=SimpleNamespace(yaw=0.0, pitch=0.0, roll=0.0))

        def set_transform(self, transform):
            self.pose = deepcopy(transform)

    camera = Camera()
    tree = ast.parse((root / "protocol" / filename).read_text())
    statements = next(node.body for node in ast.walk(tree)
                      if isinstance(node, ast.With) and any(
                          isinstance(child, ast.Assign) and any(
                              isinstance(target, ast.Name) and target.id == "cameras"
                              for target in child.targets) for child in node.body))
    start = next(i for i, node in enumerate(statements) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "cameras" for target in node.targets))
    end = next(i for i, node in enumerate(statements) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "queues" for target in node.targets))
    setup = ast.Module(body=statements[start + 1:end], type_ignores=[])
    namespace = {"world": world, "cameras": {"E": camera}, "JIT": amplitude,
                 "args": SimpleNamespace(jitter=amplitude), "seed_s": "18036"}
    exec(compile(setup, filename, "exec"), namespace)
    assert camera.pose.location == (50.0, 80.0, 10.0)
    assert world.ticks == int(amplitude > 0)

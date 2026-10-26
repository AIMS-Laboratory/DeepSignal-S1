from types import SimpleNamespace

import pytest

from deepsignal_s1.scene import CameraScene


@pytest.mark.parametrize('synchronous', [False, True])
def test_cleanup_drains_camera_callbacks(synchronous):
    calls = []
    scene = object.__new__(CameraScene)
    camera = SimpleNamespace(stop=lambda: calls.append('stop'), destroy=lambda: calls.append('destroy'))
    scene.trace = scene.encoder = None
    scene.cameras, scene.queues, scene.vehicles = {'E': camera}, {'E': object()}, {}
    scene.visuals, scene.native, scene.hidden = [], [], set()
    scene.original_settings = SimpleNamespace(synchronous_mode=synchronous)
    scene.original_weather = object()
    scene.world = SimpleNamespace(apply_settings=lambda s: calls.append('settings'),
                                  set_weather=lambda w: calls.append('weather'),
                                  tick=lambda t: calls.append('tick'),
                                  wait_for_tick=lambda t: calls.append('wait'))
    scene.__exit__(None, None, None)
    assert calls == ['stop', 'destroy', 'settings', 'weather', 'tick' if synchronous else 'wait']
    assert scene.cameras == scene.queues == scene.vehicles == {}

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fusion_manifest_keeps_current_release_separate_from_history():
    current = json.loads((ROOT / 'reproduction/fusion-release-matrix.json').read_text())
    historical = json.loads((ROOT / 'reproduction/release-matrix.json').read_text())
    assert current['release'] == 'DeepSignal-S1-1.0'
    assert historical['release'] == 'v0.2.0'
    assert set(current['conditions']) == {'clean', 'df9', 'mb31', 'angle15', 'shake5'}
    assert current['comparison_policy']['clean'] == ['s1', 'fixed', 'visual-pressure']
    assert current['comparison_policy']['special'] == ['s1', 'visual-pressure']
    assert current['comparison_policy']['fixed_baseline'] == 'engineering-fixed'
    assert current['protocol'] == {
        'phase_mode': 'skip', 'observation_window_s': 4, 'frame_offsets_s': [-4, -2, 0],
        'green_tail_s': 5, 'yellow_s': 3, 'all_red_s': 2, 'green_total_bounds_s': [6, 60],
    }
    assert current['suites']['town10hd-fusion-pilot']['runtime'] == 'CARLA-0.9.16'
    clean = current['suites']['nansha-fusion-clean']
    assert clean['model_version'] == 'DeepSignal-S1-1.0'
    assert clean['allowed_conditions'] == ['clean']
    source = clean['tags_from']
    assert source == {'manifest': 'release-matrix.json', 'suite': 'nansha', 'condition': 'clean'}
    assert len(historical['suites'][source['suite']]['conditions'][source['condition']]) == 72


def test_reproduce_maps_current_conditions_to_shared_visual_profile(tmp_path, monkeypatch):
    module = load_script('reproduce')
    observed = {}

    def call(command, **kwargs):
        observed.update(command=command, **kwargs)
        return 0

    monkeypatch.setattr(module.subprocess, 'call', call)
    monkeypatch.setattr(sys, 'argv', ['reproduce.py', '--scene', 'town10hd',
                                    '--controller', 'visual-pressure', '--tag', 'balanced-18040',
                                    '--condition', 'shake5', '--output', str(tmp_path)])
    assert module.main() == 0
    assert observed['env']['DS_VISUAL_CONDITION'] == 'shake5'
    assert observed['env']['MP_JITTER'] == '0'
    assert observed['command'][1].endswith('town_pressure.py')


def test_visual_profiles_are_deterministic_and_use_simulation_time(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'reproduction/protocol'))
    from visual_perturbation import VisualPerturbation

    class Camera:
        def __init__(self):
            self.transform = SimpleNamespace(rotation=SimpleNamespace(yaw=10.0, pitch=-20.0, roll=1.0))

        def get_transform(self):
            return deepcopy(self.transform)

        def set_transform(self, transform):
            self.transform = deepcopy(transform)

    first = Camera()
    second = Camera()
    a = VisualPerturbation('angle15', 18040)
    b = VisualPerturbation('angle15', 18040)
    a.bind({'E': first})
    b.bind({'E': second})
    assert a.parameters == b.parameters
    assert abs(first.transform.rotation.yaw - 10.0) == 15.0
    assert abs(first.transform.rotation.pitch + 20.0) == 8.0
    assert first.transform.rotation.roll == 1.0

    shake = VisualPerturbation('shake5', 18040)
    camera = Camera()
    shake.bind({'E': camera})
    shake.move(2.0)
    at_two = deepcopy(camera.transform.rotation)
    shake.move(2.0)
    assert camera.transform.rotation.__dict__ == at_two.__dict__
    shake.move(3.0)
    assert camera.transform.rotation.__dict__ != at_two.__dict__


@pytest.mark.parametrize('filename', ['town_s1.py', 'town_pressure.py'])
def test_current_angle_reads_published_pose_after_lane_markings(filename):
    text = (ROOT / 'reproduction/protocol' / filename).read_text()
    assert text.index('mount_junction_markings(world, client, session, NET)') < text.index('visual.bind(cameras)')
    assert "visual.condition in ('angle15', 'shake5')" in text


def test_df9_and_mb31_apply_exact_image_parameters(monkeypatch):
    pytest.importorskip('cv2')
    monkeypatch.syspath_prepend(str(ROOT / 'reproduction/protocol'))
    from visual_perturbation import VisualPerturbation

    image = np.zeros((41, 41, 3), dtype=np.uint8)
    image[20, 20] = 255
    defocused = VisualPerturbation('df9', 1).image(image)
    motion = VisualPerturbation('mb31', 1).image(image)
    assert defocused[20, 20, 0] < 255
    assert np.count_nonzero(motion[20, :, 0]) == 31
    assert np.count_nonzero(motion[:, 20, 0]) == 1


def test_signal_trace_validates_five_second_tail(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'reproduction/protocol'))
    from evaluation_trace import SignalTrace

    trace = SignalTrace()
    trace.switch(10.0, 'ew_straight', 'ns_straight')
    trace.stage(15.0, 'ew_straight', 'y')
    trace.stage(18.0, 'all_red', 'r')
    trace.stage(20.0, 'ns_straight', 'G')
    assert trace.metadata(20.0)['errors'] == []


def test_fusion_runner_rejects_wrong_model_without_launching(tmp_path, monkeypatch):
    module = load_script('run_fusion_matrix')

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({'model_version': 'DeepSignal-S1-1.0-candidate'}).encode()

    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *args, **kwargs: Response())
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: pytest.fail('run launched'))
    monkeypatch.setattr(sys, 'argv', ['run_fusion_matrix.py', '--suite', 'nansha-fusion-pilot',
                                    '--controller', 's1', '--condition', 'clean',
                                    '--output', str(tmp_path)])
    with pytest.raises(RuntimeError, match='requires DeepSignal-S1-1.0'):
        module.main()


def test_fusion_runner_loads_suite_choices_from_manifest_and_limits_clean_suite(tmp_path, monkeypatch):
    module = load_script('run_fusion_matrix')
    monkeypatch.setattr(sys, 'argv', ['run_fusion_matrix.py', '--suite', 'nansha-fusion-clean',
                                    '--controller', 'visual-pressure', '--condition', 'df9',
                                    '--output', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())

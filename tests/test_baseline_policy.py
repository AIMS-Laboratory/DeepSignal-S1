from pathlib import Path

import pytest

from deepsignal_s1 import cli, runner
from deepsignal_s1.data import write_json


def test_episode_rejects_fixed_special_before_creating_outputs(tmp_path):
    target = tmp_path / 'run'
    with pytest.raises(ValueError, match='engineering fixed'):
        runner.run_episode({}, {}, target, controller='fixed', condition='defocus', cpu=True)
    assert not target.exists()


def test_fixed_suite_runs_only_clean_cases(tmp_path, monkeypatch):
    suite = {'duration_s': 300, 'seeds': [1], 'cases': [
        {'scene': 'demo', 'scene_file': 'demo.json', 'regime': 'east-west', 'condition': condition}
        for condition in ('clean', 'defocus')]}
    path = tmp_path / 'suite.json'
    write_json(path, suite)
    calls = []
    monkeypatch.setattr(cli, 'load_scene', lambda path: {'id': 'demo'})
    monkeypatch.setattr(cli, 'build_plan', lambda *args: {'scene': 'demo'})

    def run(*args, **kwargs):
        calls.append(kwargs['condition'])
        return {'metrics': {}}

    monkeypatch.setattr(runner, 'run_episode', run)
    assert cli.main(['run-suite', '--suite', str(path), '--controller', 'fixed', '--cpu',
                     '--output', str(tmp_path / 'runs')]) == 0
    assert calls == ['clean']


def test_current_scenes_do_not_offer_other_fixed_references():
    root = Path(__file__).resolve().parents[1]
    assert not list((root / 'scenarios').rglob('scene.tuned-reference.json'))

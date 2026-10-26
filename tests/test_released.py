import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_released_tables_recompute():
    module = load_script('summarize_released')
    manifest = json.loads((ROOT / 'reproduction/release-matrix.json').read_text())
    fixed = json.loads((ROOT / 'results/engineering-fixed-2026-10-26.json').read_text())['records']
    report = module.build_report(manifest, ROOT / 'reproduction/reference-results', fixed)
    blocks = {(b['suite'], b['condition']): b for b in report['blocks']}
    ns = blocks['nansha', 'clean']
    assert ns['improvement_vs_engineering_fixed_pct'] == pytest.approx(15.988, abs=0.001)
    fixed_comparison = ns['engineering_fixed_comparison']
    assert fixed_comparison['successful_pairs'] == 72
    assert fixed_comparison['s1_wins'] == 56
    assert fixed_comparison['s1_losses'] == 16
    assert fixed_comparison['ties'] == 0
    assert fixed_comparison['s1_win_rate_pct'] == pytest.approx(100 * 56 / 72)
    assert ns['junctions_within_5pct'] == 5
    ns_defocus = blocks['nansha', 'defocus-2.5']
    assert ns_defocus['successful_pairs'] == 65
    assert len(ns_defocus['failures']['s1']) == 6
    assert len(ns_defocus['failures']['visual-pressure']) == 1
    assert ns_defocus['improvement_vs_yolo_pct'] == pytest.approx(25.6904, abs=0.001)
    # The YOLO-only failure must not remove a valid S1 versus fixed pair.
    defocus_fixed = ns_defocus['engineering_fixed_comparison']
    assert defocus_fixed['successful_pairs'] == 66
    assert defocus_fixed['s1_wins'] == 46
    assert defocus_fixed['s1_losses'] == 20
    assert defocus_fixed['improvement_pct'] == pytest.approx(10.043, abs=0.001)
    town = blocks['town10hd-archive', 'clean']
    assert town['expected_pairs'] == town['successful_pairs'] == 20
    assert town['improvement_vs_yolo_pct'] == pytest.approx(3.1294, abs=0.001)
    assert town['improvement_vs_engineering_fixed_pct'] == pytest.approx(36.2079, abs=0.001)


def test_fixed_comparison_distinguishes_exact_ties_from_small_wins(tmp_path):
    module = load_script('summarize_released')
    manifest = {'release': 'test', 'suites': {'nansha': {
        'metric': 'J_H', 'model_version': 'test-model', 'runtime': 'test', 'horizon_s': 1298,
        'conditions': {'clean': ['J01-win', 'J01-tie', 'J01-loss']}}}}
    for controller in ['s1', 'visual-pressure']:
        directory = tmp_path / 'nansha/clean' / controller
        directory.mkdir(parents=True)
        for tag, value in [('J01-win', 99.99), ('J01-tie', 100), ('J01-loss', 101)]:
            (directory / (tag + '.json')).write_text(json.dumps({
                'model_version': 'test-model', 'fail': None, 'J_H': value}))
    fixed = [{'scene': 'nansha', 'tag': tag, 'J_H': 100, 'fail': None}
             for tag in ['J01-win', 'J01-tie', 'J01-loss']]
    report = module.build_report(manifest, tmp_path, fixed)
    comparison = report['blocks'][0]['engineering_fixed_comparison']
    assert (comparison['s1_wins'], comparison['ties'], comparison['s1_losses']) == (1, 1, 1)


@pytest.mark.parametrize('controller', ['s1', 'visual-pressure'])
@pytest.mark.parametrize('condition', ['clean', 'defocus-2.5'])
def test_archive_entry_uses_legacy_protocol(controller, condition, tmp_path, monkeypatch):
    module = load_script('reproduce_archive')
    observed = {}
    def run(command, **kwargs):
        observed.update(command=command, **kwargs)
        return 0
    monkeypatch.setattr(module.subprocess, 'call', run)
    monkeypatch.setattr(sys, 'argv', ['reproduce_archive.py', '--controller', controller,
                                    '--condition', condition, '--tag', 'balanced-18040',
                                    '--output', str(tmp_path)])
    assert module.main() == 0
    assert 'legacy-town' in observed['command'][1]
    if controller == 's1':
        command = observed['command']
        assert command[command.index('--jitter') + 1] == '0'
    else:
        assert observed['env']['MP_JITTER'] == '0'


def test_archive_has_original_runtime_and_assets():
    for name in ['town_s1.py', 'town_pressure.py', 'town_pressure_degraded.py']:
        text = (ROOT / 'reproduction/legacy-town' / name).read_text()
        assert "('0.9.16', '0.9.16')" in text
        assert 'vehicle.tesla.model3' in text
        assert 'mount_junction_markings(world, client, session, NET)' in text


def test_published_runner_rejects_wrong_model(tmp_path, monkeypatch):
    module = load_script('run_released_matrix')
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({'model_version': 'DeepSignal-S1-1.0-candidate'}).encode()
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: Response())
    monkeypatch.setattr(sys, 'argv', ['run_released_matrix.py', '--suite', 'town10hd-archive',
                                    '--controller', 's1', '--condition', 'clean', '--output', str(tmp_path)])
    with pytest.raises(RuntimeError, match='requires DeepSignal-S1-Town10HD-1.0-archive'):
        module.main()


def test_fixed_release_runner_retains_each_case(tmp_path, monkeypatch):
    module = load_script('run_released_matrix')
    def run(command, **kwargs):
        destination = Path(command[command.index('--output') + 1])
        destination.mkdir(parents=True, exist_ok=True)
        tag = command[command.index('--tag') + 1]
        (destination / 'result.json').write_text(json.dumps({
            'tag': tag, 'J': 123.0, 'baseline': 'engineering-fixed', 'fail': None}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['run_released_matrix.py', '--suite', 'town10hd-archive',
                                    '--controller', 'fixed', '--condition', 'clean', '--output', str(tmp_path)])
    assert module.main() == 0
    directory = tmp_path / 'town10hd-archive/clean/fixed'
    assert len(list(directory.glob('*/result.json'))) == 20
    assert len(load_script('summarize_released').load_fixed(tmp_path)) == 20

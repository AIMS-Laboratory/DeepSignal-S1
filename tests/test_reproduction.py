import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


def test_town_fixed_preserves_first_green_not_formal_window(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1] / 'reproduction'
    for sub in ('src', 'protocol', 'scripts/carla'):
        monkeypatch.syspath_prepend(str(root / sub))
    spec = importlib.util.spec_from_file_location('fixed_repro', root / 'protocol/fixed_baseline.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import town_fixed
    from deepsignal.decision_loop import Action

    observed = []
    def run(tag):
        for phase, elapsed in [('ew_straight', 26), ('ew_left', 1), ('ew_straight', 26)]:
            pending = SimpleNamespace(phase=phase, green_elapsed_at_state=elapsed, deadline=50)
            observed.append(town_fixed.table_answer(pending, town_fixed.TABLE_GREEN))
        return 123
    original_answer = town_fixed.table_answer
    monkeypatch.setattr(town_fixed, 'run_fixed_arm', run)
    monkeypatch.setattr(town_fixed, 'table_answer', original_answer)
    module.town('balanced-18036', tmp_path)
    assert observed == [Action.EXTEND, Action.END, Action.END]


def test_matrix_has_all_fixed_plans():
    import json
    root = Path(__file__).resolve().parents[1] / 'reproduction'
    cases = json.loads((root / 'matrix.json').read_text())['cases']
    assert len(cases) == 112
    assert sum(c['scene'] == 'nansha' for c in cases) == 72
    for case in cases:
        assert (root / case['plan']).is_file()


def test_nansha_networks_are_portable():
    import json
    root = Path(__file__).resolve().parents[1] / 'reproduction'
    configs = list((root / 'configs/junctions').glob('nansha-*-v2.json'))
    assert len(configs) == 9
    for path in configs:
        network = Path(json.loads(path.read_text())['default_network'])
        assert not network.is_absolute()
        assert (root / network).is_file()


def test_town_angle_arms_use_identical_random_seed():
    import ast
    root = Path(__file__).resolve().parents[1] / 'reproduction/protocol'
    seeds = []
    for name in ('town_s1.py', 'town_pressure.py'):
        tree = ast.parse((root / name).read_text())
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'Random')
        expression = ast.Expression(body=call.args[0])
        seeds.append(eval(compile(expression, name, 'eval'), {'int': int},
                          {'seed_s': '18036', 'args': SimpleNamespace(jitter=8), 'JIT': 8}))
    assert seeds == [18116, 18116]

import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("filename", ["town_s1.py", "town_pressure.py", "town_pressure_degraded.py"])
@pytest.mark.parametrize("green", [6.0, 31.0, 60.0])
def test_switch_preserves_committed_green_tail(filename, green):
    path = Path(__file__).resolve().parents[1] / "reproduction/protocol" / filename
    tree = ast.parse(path.read_text())
    loop = next(node for node in ast.walk(tree) if isinstance(node, ast.While)
                and isinstance(node.test, ast.BoolOp)
                and isinstance(node.test.values[0], ast.Name) and node.test.values[0].id == "trans")
    events = []
    namespace = {
        "trans": (green - 5.0, "decide", "ew_straight"),
        "seg": {"s": 0.0, "G": green, "ph": "ew_straight"},
        "now": green - 5.0, "last_ge": {}, "PHASES": ("ew_straight", "ew_left", "ns_straight", "ns_left"),
        "infer_decide": lambda *args: (("switch", "ns_straight"), 1.0),
        "mp_decide": lambda *args: ("switch", "ns_straight"),
        "set_st": lambda state: events.append(state), "dec_log": [], "fail": [None],
        "pend": None, "T_END": 518.0, "ended": False,
    }
    code = ast.Module(body=[loop], type_ignores=[])
    exec(compile(code, filename, "exec"), namespace)
    assert events == [], "A switch decision must not turn yellow five seconds early"
    assert namespace["trans"] == (green, "y", "ew_straight")
    assert namespace["pend"] == (green + 5.0, "ns_straight")
    assert namespace["last_ge"]["ew_straight"] == green


@pytest.mark.parametrize("filename", ["town_s1.py", "town_pressure.py", "town_pressure_degraded.py"])
def test_clearance_near_horizon_does_not_end_measurement_early(filename):
    path = Path(__file__).resolve().parents[1] / "reproduction/protocol" / filename
    tree = ast.parse(path.read_text())
    stop = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                and any(isinstance(child, ast.Break) for child in node.body)
                and any(isinstance(child, ast.Name) and child.id == "T_END" for child in ast.walk(node.test)))
    test = ast.Expression(body=stop.test)
    assert not eval(compile(test, filename, "eval"), {"now": 517.0, "T_END": 518.0, "ended": True})


@pytest.mark.parametrize("filename", ["town_s1.py", "town_pressure.py", "town_pressure_degraded.py"])
@pytest.mark.parametrize("maximum_green", [6.0, 60.0])
def test_event_loop_executes_same_green_yellow_and_all_red(filename, maximum_green):
    path = Path(__file__).resolve().parents[1] / "reproduction/protocol" / filename
    tree = ast.parse(path.read_text())
    loop = next(node for node in ast.walk(tree) if isinstance(node, ast.While)
                and isinstance(node.test, ast.BoolOp)
                and isinstance(node.test.values[0], ast.Name) and node.test.values[0].id == "trans")
    phases = ("ew_straight", "ew_left", "ns_straight", "ns_left")
    events = [(0.0, (phases[0], "G"))]
    namespace = {"trans": (1.0, "decide", phases[0]),
                 "seg": {"s": 0.0, "G": 6.0, "ph": phases[0]},
                 "last_ge": {}, "PHASES": phases, "dec_log": [], "fail": [None],
                 "pend": None, "T_END": 518.0, "ended": False}
    def decision(tt, phase, green, *unused):
        return "extend" if green < maximum_green else ("switch", phases[(phases.index(phase) + 1) % 4])
    namespace.update(infer_decide=lambda *args: (decision(*args), 1.0), mp_decide=decision,
                     set_st=lambda state: events.append((namespace["now"], state)))
    code = compile(ast.Module(body=[loop], type_ignores=[]), filename, "exec")
    for step in range(1, 2001):
        namespace["now"] = round(step * 0.1, 1)
        exec(code, namespace)
    assert len(events) > 5
    expected = {"G": maximum_green, "y": 3.0, "r": 2.0}
    for (start, (_, color)), (end, _) in zip(events, events[1:]):
        assert end - start == pytest.approx(expected[color])


@pytest.mark.parametrize("filename", ["town_pressure.py", "town_pressure_degraded.py"])
def test_first_pressure_decision_uses_real_observations(filename):
    path = Path(__file__).resolve().parents[1] / "reproduction/protocol" / filename
    tree = ast.parse(path.read_text())
    handoff = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                   and any(isinstance(child, ast.Name) and child.id == "boundary"
                           for child in ast.walk(node.test)))
    calls = []
    def decide(*args):
        calls.append(args)
        return "extend"
    namespace = {"stage": "pre", "boundary": True, "green_end": {"ew_straight": 31.0},
                 "green_start": {"ew_straight": 0.0}, "now": 26.0,
                 "PHASES": ("ew_straight", "ew_left", "ns_straight", "ns_left"),
                 "mp_decide": decide, "fail": [None]}
    once = ast.For(target=ast.Name(id="_once", ctx=ast.Store()),
                   iter=ast.Tuple(elts=[ast.Constant(value=0)], ctx=ast.Load()),
                   body=handoff.body, orelse=[])
    code = ast.fix_missing_locations(ast.Module(body=[once], type_ignores=[]))
    exec(compile(code, filename, "exec"), namespace)
    assert len(calls) == 1
    assert calls[0][:3] == (26.0, "ew_straight", 31.0)

from __future__ import annotations
import argparse
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import traci
from deepsignal.decision_loop import EPS, Action, FinalAnswer, GreenBounds, LoopConfig, PhaseChange, SignalController, SignalUpdate
from deepsignal.green_tables import green_table_greens
from deepsignal.ue4_junction import TARGET_TLS_ID, movement_groups, motor_links
PHASE_ORDER = ('ew_straight', 'ew_left', 'ns_straight', 'ns_left')

def fixed_controller(raw: dict, net_file: Path, green_table: str='default', handover_at: float | None=None):
    run_green = green_table_greens(green_table, net_file)
    greens = sorted(set(run_green.values()))
    per_phase = {phase: GreenBounds(run_green[phase], run_green[phase]) for phase in run_green}
    config = LoopConfig(step=float(raw['step']), observation_window=1.0, reservation=1.0, extension_step=1.0, countdown=float(raw['countdown']), yellow=float(raw['yellow']), all_red=float(raw['all_red']), min_green=float(greens[0]), max_green=float(greens[-1]), per_phase_bounds=per_phase, fixed_green_by_phase=dict(run_green), post_handover_green_by_phase={})
    controller = SignalController(config=config, phases=PHASE_ORDER, groups=movement_groups(net_file), link_count=max([*motor_links(net_file)[0], *motor_links(net_file)[1]]) + 1, initial_red=float(raw['initial_red']), handover_at=handover_at)
    return (controller, run_green)

def find_formal_start(controller: SignalController, warmup_min: float) -> float:
    probe = SignalController(config=controller.config, phases=controller.phases, groups=controller.groups, link_count=controller.link_count, initial_red=controller.initial_red)
    t = 0.0
    while t < warmup_min + 4.0 * (controller.config.yellow + controller.config.all_red + max((g for g in controller.config.fixed_green_by_phase.values()))) + 1.0:
        t = round(t + controller.config.step, 6)
        for event in probe.tick(t, status=None, window=None):
            if isinstance(event, PhaseChange) and event.to_phase == 'ew_straight' and (event.time >= warmup_min):
                return event.time
    raise RuntimeError('未找到预热后的相位边界')

def load_raw(config_path: Path, seed: int) -> dict:
    raw = json.loads(config_path.read_text())
    raw['seed'] = seed
    return raw

def start_sumo(net: Path, routes: Path, raw: dict, tripinfo: Path, label: str):
    traci.start(['sumo', '--net-file', str(net), '--route-files', str(routes), '--step-length', str(raw['step']), '--time-to-teleport', '-1', '--no-step-log', 'true', '--seed', str(raw['seed']), '--tripinfo-output', str(tripinfo), '--tripinfo-output.write-unfinished', 'true'], label=label)
    return traci.getConnection(label)

def tripinfo_metrics(tripinfo: Path, formal_ids: set[str]) -> dict:
    root = ET.parse(tripinfo).getroot()
    rows = [t for t in root.findall('tripinfo') if t.attrib['id'] in formal_ids]
    durations = [float(t.attrib['duration']) for t in rows]
    return {'n': len(rows), 'mean_duration': sum(durations) / len(durations) if durations else None}

def adaptive_controller(raw: dict, net_file: Path, table_green: dict[str, float], min_green: float=6.0, max_green: float=60.0):
    per_phase = {phase: GreenBounds(float(min_green), float(max_green)) for phase in table_green}
    config = LoopConfig(step=float(raw['step']), observation_window=1.0, reservation=1.0, extension_step=1.0, countdown=float(raw['countdown']), yellow=float(raw['yellow']), all_red=float(raw['all_red']), min_green=float(min_green), max_green=float(max_green), per_phase_bounds=per_phase, fixed_green_by_phase={}, post_handover_green_by_phase={})
    return SignalController(config=config, phases=PHASE_ORDER, groups=movement_groups(net_file), link_count=max([*motor_links(net_file)[0], *motor_links(net_file)[1]]) + 1, initial_red=float(raw['initial_red']), handover_at=None)

def table_answer(request, table_green: dict[str, float]) -> Action:
    g_tbl = table_green[request.phase]
    return Action.END if request.green_elapsed_at_state >= g_tbl - 5.0 else Action.EXTEND

def run_fork_headless(net: Path, routes: Path, raw: dict, formal_ids: set[str], out: Path, label: str, table_green: dict[str, float], fork_at: float | None=None, fork_action: Action | None=None, horizon: float | None=None):
    conn = start_sumo(net, routes, raw, out / f'tripinfo-{label}.xml', label)
    controller = adaptive_controller(raw, net, table_green)
    update = controller.current_update(0.0)
    end = raw['formal_end'] if horizon is None else horizon
    fed_fork = fork_action is None
    n_requests = n_model = 0
    t0 = time.monotonic()
    try:
        while True:
            conn.trafficlight.setRedYellowGreenState(str(TARGET_TLS_ID), update.state)
            conn.simulationStep()
            now = conn.simulation.getTime()
            status = None
            pending = controller.pending
            settling = pending is not None and now + EPS >= pending.deadline
            if settling:
                n_requests += 1
                if fork_action is not None and (not fed_fork) and (now >= fork_at):
                    action = fork_action
                    fed_fork = True
                elif fork_action is not None and fed_fork and (now >= fork_at):
                    action = Action.EXTEND
                else:
                    action = table_answer(pending, table_green)
                if action in pending.legal_actions:
                    status = FinalAnswer(action=action, raw_output='probe', complete=True, wall_seconds=0.0)
                    n_model += 1
            for event in controller.tick(now, status=status, window={'frame_times': (now,), 'signal_history': ()}):
                if isinstance(event, SignalUpdate):
                    update = event
            if now >= end:
                break
    finally:
        conn.close()
    wall = time.monotonic() - t0
    m = tripinfo_metrics(out / f'tripinfo-{label}.xml', formal_ids)
    m.update({'wall_s': round(wall, 2), 'sim_s': end, 'requests': n_requests, 'answered': n_model, 'fork_fed': fed_fork})
    return m

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--d0', type=Path, required=True, help='d0 回合目录（network/routes/plan）')
    ap.add_argument('--config', type=Path, default=Path('configs/vlm-realtime-control/episode-balanced.formal.json'))
    ap.add_argument('--seed', type=int, default=1919)
    ap.add_argument('--fork-at', type=float, default=120.0, help='formal 窗内决策时刻')
    ap.add_argument('--horizon', type=float, default=90.0, help='分叉时长 H（仿真秒）')
    ap.add_argument('--out', type=Path, default=Path('out/s1-e0/fork-probe'))
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    net = args.d0 / 'network' / 'junction.net.xml'
    routes = args.d0 / 'routes.rou.xml'
    raw = load_raw(args.config, args.seed)
    plan = json.loads((args.d0 / 'plan.json').read_text())
    formal_ids = {v['vehicle_id'] for v in plan['vehicles'] if v.get('cohort') == 'formal'}
    (ctrl_probe, table_green) = fixed_controller(raw, net, green_table='default')
    formal_start = find_formal_start(ctrl_probe, float(raw['warmup_min']))
    formal_end = formal_start + float(raw['window_duration'])
    raw['formal_end'] = formal_end + float(raw['clearance_limit'])
    result = {'formal_ids': len(formal_ids), 'formal_window': [formal_start, formal_end], 'table_green': table_green}
    full = run_fork_headless(net, routes, raw, formal_ids, out, 'full-a', table_green)
    full_b = run_fork_headless(net, routes, raw, formal_ids, out, 'full-b', table_green)
    result['full_a'] = full
    result['full_b'] = full_b
    d0 = json.loads((args.d0 / 'report.json').read_text())
    result['cosim_mean_journey'] = d0['metrics'].get('mean_journey_time')
    result['cosim_mean_travel'] = d0['metrics'].get('mean_travel_time')
    forks = {}
    for (name, action) in (('extend', Action.EXTEND), ('end', Action.END), ('default-a', None), ('default-b', None)):
        forks[name] = run_fork_headless(net, routes, raw, formal_ids, out, f'fork-{name}', table_green, fork_at=args.fork_at, fork_action=action, horizon=args.fork_at + args.horizon)
    result['forks'] = forks
    result['params'] = {'fork_at': args.fork_at, 'H': args.horizon}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    (out / 'probe-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()

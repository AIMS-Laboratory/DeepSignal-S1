"""Engineering fixed timing under the archived paired-test protocols."""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from intersection_metrics import IntersectionMetrics
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'protocol'), str(ROOT / 'scripts/carla')]

def nansha(tag, output):
    import traci
    from deepsignal.demand_plan import PlannedArrivals
    from nansha_rules import load_ns
    from network_routes import probe_links, state_str, _imports
    cfg = load_ns(tag.split('-')[0])
    plan = PlannedArrivals.load(ROOT / f'out/nansha/plans-sft-final/{tag}/plan.json')
    routes = _imports(cfg)(cfg['net'], output, plan.vehicles)
    links = probe_links(cfg)
    logic = next((t for t in ET.parse(cfg['net']).getroot().findall('tlLogic') if t.get('id') == cfg['tls']))
    width = len(logic.find('phase').get('state'))
    planned = {v.vehicle_id: v.planned_depart for v in plan.vehicles if v.cohort == 'formal'}
    label = f'engineering-{tag}'
    traci.start(['sumo', '--net-file', cfg['net'], '--route-files', str(routes), '--step-length', '0.1', '--time-to-teleport', '-1', '--no-step-log', 'true', '--seed', str(plan.seed), '--tripinfo-output', str(output / 'tripinfo.xml'), '--tripinfo-output.write-unfinished', 'true'], label=label)
    conn = traci.getConnection(label)
    evaluation = IntersectionMetrics(conn, cfg['tls'], end=1298.0)
    phases = cfg['phases']
    (index, stage, deadline) = (0, 'initial', 0.1)
    arrivals = {}
    try:
        conn.trafficlight.setRedYellowGreenState(cfg['tls'], 'r' * width)
        while True:
            conn.simulationStep()
            now = conn.simulation.getTime()
            evaluation.update(now)
            for vid in conn.simulation.getArrivedIDList():
                if vid in planned:
                    arrivals.setdefault(vid, now)
            while now + 1e-09 >= deadline:
                phase = phases[index]
                if stage in ('initial', 'red'):
                    conn.trafficlight.setRedYellowGreenState(cfg['tls'], state_str(links, width, 'G', phase))
                    (stage, deadline) = ('green', deadline + cfg['tuned'][phase])
                elif stage == 'green':
                    conn.trafficlight.setRedYellowGreenState(cfg['tls'], state_str(links, width, 'y', phase))
                    (stage, deadline) = ('yellow', deadline + cfg['yellow'][phase])
                else:
                    conn.trafficlight.setRedYellowGreenState(cfg['tls'], 'r' * width)
                    index = (index + 1) % len(phases)
                    (stage, deadline) = ('red', deadline + cfg['all_red'][phases[index]])
            if now >= 1298 - 1e-09 or len(arrivals) == len(planned):
                break
    finally:
        conn.close()
    evaluation.write(output / f'{tag}-metrics.json', output / 'tripinfo.xml', planned)
    return {'tag': tag, 'J_H': round(sum((min(arrivals.get(v, 1298), 1298) - d for (v, d) in planned.items())) / len(planned), 2), 'N': len(planned), 'arrived': len(arrivals), 'unfinished': len(planned) - len(arrivals), 'fail': None, 'table': cfg['tuned'], 'baseline': 'engineering-fixed', 'horizon_s': 1298}

def town(tag, output):
    import town_fixed
    import sumo_fork_probe as sfp
    from deepsignal.decision_loop import Action
    table = {'ew_straight': 31.0, 'ew_left': 6.0, 'ns_straight': 31.0, 'ns_left': 6.0}
    original = town_fixed.table_answer
    first_phase = next(iter(table))
    warmup = True

    def engineering_answer(pending, unused):
        nonlocal warmup
        if pending.phase != first_phase:
            warmup = False
        if warmup:
            return original(pending, town_fixed.TABLE_GREEN)
        return Action.END if pending.green_elapsed_at_state >= table[pending.phase] - 5.0 else Action.EXTEND
    town_fixed.table_answer = engineering_answer
    town_fixed.B2 = output
    (output / 'tripinfo').mkdir(parents=True, exist_ok=True)
    value = town_fixed.run_fixed_arm(tag)
    return {'tag': tag, 'J': value, 'fail': None, 'table': table, 'baseline': 'engineering-fixed', 'horizon_s': 518}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', choices=['nansha', 'town10hd'], required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    import os
    os.chdir(ROOT)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = (nansha if args.scene == 'nansha' else town)(args.tag, output)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
if __name__ == '__main__':
    main()

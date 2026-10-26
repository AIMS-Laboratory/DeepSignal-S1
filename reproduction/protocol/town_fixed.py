import json
from pathlib import Path
from sumo_fork_probe import adaptive_controller, start_sumo, table_answer
import sumo_fork_probe as sfp
from deepsignal.decision_loop import FinalAnswer
from episode_settings import make_raw, TABLE_GREEN, NET
from signal_states import warm_states
T_END = 518.0
B2 = Path('protocol')

def run_fixed_arm(tag):
    warm_states()
    (cond, seed_s) = tag.rsplit('-', 1)
    raw = make_raw(cond, int(seed_s))
    routes = Path(f'out/s1-e0/plans/nc-{tag}/routes.rou.xml')
    rp = json.loads(Path(f'out/s1-e0/plans/nc-{tag}/plan.json').read_text())
    planned = {v['vehicle_id']: v['planned_depart'] for v in rp['vehicles'] if v['cohort'] == 'formal'}
    formal_set = set(planned)
    label = f'bfix-{tag}'[:60]
    conn = start_sumo(NET, routes, raw, B2 / 'tripinfo' / f'{label}.xml', label)
    c = adaptive_controller(raw, NET, TABLE_GREEN)
    update = c.current_update(0.0)
    arr = {}
    try:
        while True:
            conn.trafficlight.setRedYellowGreenState(str(sfp.TARGET_TLS_ID), update.state)
            conn.simulationStep()
            now = conn.simulation.getTime()
            for v in conn.simulation.getArrivedIDList():
                if v in formal_set and v not in arr:
                    arr[v] = now
            status = None
            p_ = c.pending
            if p_ is not None and now + sfp.EPS >= p_.deadline:
                a = table_answer(p_, TABLE_GREEN)
                if a in p_.legal_actions:
                    status = FinalAnswer(action=a, raw_output='x', complete=True, wall_seconds=0)
            for e in c.tick(now, status=status, window={'frame_times': (now,), 'signal_history': ()}):
                if isinstance(e, sfp.SignalUpdate):
                    update = e
            if now >= T_END - 1e-09:
                break
    finally:
        conn.close()
    J = round(sum((min(arr.get(v, T_END), T_END) - d for (v, d) in planned.items() if d < T_END)), 1)
    return J

import os as _os
import numpy as _np
_NS_DEG = _os.environ.get('NS_DEG', 'none')
_NS_DEGP = float(_os.environ.get('NS_DEGP', '9'))
if _NS_DEG == 'mb':
    _k = _np.zeros((1, int(_NS_DEGP)), dtype=_np.float32)
    _k[0, :] = 1.0 / int(_NS_DEGP)

    def _deg(img):
        return cv2.filter2D(img, -1, _k)
elif _NS_DEG == 'df':

    def _deg(img):
        return cv2.GaussianBlur(img, (0, 0), _NS_DEGP)
else:

    def _deg(img):
        return img
_NS_J8 = _NS_DEG == 'j8'
import argparse, atexit, base64, json, os, random, sys, time, urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT = Path.cwd()
TAG0 = next((a for a in sys.argv[1:] if not a.startswith('-')), None)
if TAG0 is None:
    raise SystemExit('用法: ns_b_eval.py <tag> [--serve URL] [--out DIR]')
os.environ['DEEPSIGNAL_JUNCTION_PROFILE'] = str(ROOT / f"configs/junctions/nansha-{TAG0.split('-')[0].lower()}-v2.json")
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts/carla'))
sys.path.insert(0, str(ROOT / 'protocol'))
import traci
import cv2
from run_ue5_control import UE5Scene, connect_ue5
from nansha_rules import load_ns, legal_ns, TAIL, EXT, R_MAX
from network_routes import probe_links, state_str, _imports
from intersection_state import build_ns_state
from deepsignal.demand_plan import PlannedArrivals
from deepsignal.observation import carla_image_to_bgr, compose_tiled_frame
from intersection_metrics import IntersectionMetrics
STEP = 0.1
H_OFFICIAL = 1298.0

def raw_capture(scene):
    frame_id = scene.world.tick(20)
    frames = {}
    for (name, pending) in scene.queues.items():
        while True:
            frame = pending.get(timeout=20)
            if frame.frame == frame_id:
                frames[name] = carla_image_to_bgr(frame)
                break
            if frame.frame > frame_id:
                raise RuntimeError('相机帧号超过当前同步帧')
    return (frame_id, _deg(compose_tiled_frame(frames, scene.rig, draw_labels=False)))

def clean_world(client):
    world = client.get_world()
    stray = list(world.get_actors().filter('vehicle.*')) + list(world.get_actors().filter('sensor.*')) + [a for a in world.get_actors() if 'nanshasignal' in a.type_id or 'nanshadetailsignal' in a.type_id]
    if stray:
        print(f'[clean] 清理残留 actor {len(stray)} 个', flush=True)
        for a in stray:
            try:
                a.destroy()
            except RuntimeError:
                pass
        world.tick()
        left = list(world.get_actors().filter('vehicle.*')) + list(world.get_actors().filter('sensor.*')) + [a for a in world.get_actors() if 'nanshasignal' in a.type_id or 'nanshadetailsignal' in a.type_id]
        if left:
            print(f'[clean] 残留清不动（{len(left)}）→ 需重启 server', flush=True)
            raise SystemExit(2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--serve', default='http://127.0.0.1:8040')
    ap.add_argument('--out', default='protocol/ns_eval_student')
    ap.add_argument('--no-interlock', action='store_true', help='R2-C 验收：关闭协议级濒死互锁，测模型自主能力')
    args = ap.parse_args()
    TAG = args.tag
    JUN = TAG.split('-')[0]
    cfg = load_ns(JUN)
    out_json = Path(args.out) / f'{TAG}.json'
    out_json.parent.mkdir(parents=True, exist_ok=True)
    if out_json.exists():
        raise SystemExit(f'{out_json} 已存在')
    work_dir = Path(args.out) / 'frames' / TAG
    work_dir.mkdir(parents=True, exist_ok=True)
    _plans = os.environ.get('NS_PLANS_DIR', 'out/nansha/plans-sft-final')
    plan_dir = next((ROOT / _plans / TAG for _ in [0]))
    plan = PlannedArrivals.load(plan_dir / 'plan.json')
    planned = {v.vehicle_id: v.planned_depart for v in plan.vehicles if v.cohort == 'formal'}
    formal = set(planned)
    N = len(formal)
    write_routes = _imports(cfg)
    routes = write_routes(cfg['net'], work_dir, plan.vehicles)
    links = probe_links(cfg)
    tl = next((t for t in ET.parse(cfg['net']).getroot().findall('tlLogic') if t.get('id') == cfg['tls']))
    n_links = len(tl.findall('phase')[0].get('state'))
    client = connect_ue5(int(os.environ.get('NS_UE5_PORT', '25000')))
    clean_world(client)
    label = f'nsbe-{TAG}'[:50]
    tripinfo = work_dir / 'tripinfo.xml'
    traci.start(['sumo', '--net-file', str(cfg['net']), '--route-files', str(routes), '--step-length', str(STEP), '--time-to-teleport', '-1', '--no-step-log', 'true', '--seed', str(plan.seed), '--tripinfo-output', str(tripinfo), '--tripinfo-output.write-unfinished', 'true'], label=label)
    conn = traci.getConnection(label)
    evaluation = IntersectionMetrics(conn, cfg['tls'], end=H_OFFICIAL)

    def _close():
        try:
            conn.close()
        except Exception:
            pass
    atexit.register(_close)
    vh_meta = {v.vehicle_id: (v.approach, 'SR' if v.turn in ('s', 'r') else 'L') for v in plan.vehicles}
    rng = random.Random(plan.seed)
    palette = ('35,75,150', '150,35,35', '210,210,210', '40,40,40', '200,150,45')
    appearances = {v.vehicle_id: rng.choice(palette) for v in plan.vehicles}
    turn_by_vehicle = {v.vehicle_id: v.turn for v in plan.vehicles}
    P = cfg['phases']
    edges_of = cfg['approach_edges']
    arr = {}
    last_ge = {q: 0.0 for q in P}
    seg = trans = pend = None
    last_phase = [P[0]]
    ended = False
    fail = None
    n_log = []
    dec_log = []
    n_interlock = 0
    n_fail_infer = 0
    cap_sched = []
    cap_mem = {}
    n_saved = 0
    t_wall = time.monotonic()
    preview_saved = False
    camera_cfg = ROOT / f'data/NanshaTrafficProject/outputs/nansha-twin/control/data/cameras/{JUN}.json'

    def counts_now():
        d = {}
        for vid in conn.vehicle.getIDList():
            if vh_meta.get(vid) is None:
                continue
            ap = next((a for (a, e) in edges_of.items() if conn.vehicle.getRoadID(vid) == e), None)
            if ap is None:
                continue
            d[ap] = d.get(ap, 0) + 1
        return d

    def infer_decide(tt, cur, G, e, red_age):
        nonlocal n_fail_infer
        state = build_ns_state(cfg, cur, G, e, red_age)
        if state is None:
            return (None, 0.0)
        frames_b64 = []
        for dt in (4.0, 2.0, 0.0):
            hit = cap_mem.get(round(tt - dt, 1))
            if hit is None:
                raise RuntimeError(f'{TAG}@{tt:g} 决策窗缺帧 t{round(tt - dt, 1):g}')
            frames_b64.append(base64.b64encode(hit).decode())
        req = urllib.request.Request(f'{args.serve}/v1/decide', data=json.dumps({'state': state, 'frames': frames_b64}).encode(), headers={'Content-Type': 'application/json'})
        t0 = time.monotonic()
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        except Exception:
            n_fail_infer += 1
            return (None, 0.0)
        ms = (time.monotonic() - t0) * 1000
        choice = r.get('choice', '')
        if not choice or r.get('error'):
            n_fail_infer += 1
            return (None, ms)
        if choice == 'extend_5s' and 'extend_5s' in state['legal_actions']:
            return ('extend', ms)
        if choice.startswith('switch_to_'):
            p = choice.removeprefix('switch_to_')
            if f'switch_to_{p}' in state['legal_actions']:
                return (('switch', p), ms)
        return (None, ms)

    def sched_decide(T):
        cap_sched.extend([round(T - 4.0, 1), round(T - 2.0, 1), round(T, 1)])
    try:
        with UE5Scene(client, cfg['net'], work_dir, camera_config=camera_cfg) as scene:
            scene.sumo_connection = conn
            if _NS_J8:
                import carla as _carla
                _jr = random.Random(int(plan.seed))
                for (_name, _cam) in scene.cameras.items():
                    _tr = _cam.get_transform()
                    _dy = _jr.uniform(-_NS_DEGP, _NS_DEGP)
                    _dp = _jr.uniform(-_NS_DEGP, _NS_DEGP)
                    _dr = _jr.uniform(-_NS_DEGP / 2, _NS_DEGP / 2)
                    _tr.rotation.yaw += _dy
                    _tr.rotation.pitch += _dp
                    _tr.rotation.roll += _dr
                    _cam.set_transform(_tr)
                    print(f'[j8] {_name}: yaw{_dy:+.1f} pitch{_dp:+.1f} roll{_dr:+.1f}', flush=True)
                scene.world.tick(20)
            cur_state = 'r' * n_links
            conn.trafficlight.setRedYellowGreenState(cfg['tls'], cur_state)
            while True:
                conn.simulationStep()
                now = conn.simulation.getTime()
                evaluation.update(now)
                for v in conn.simulation.getArrivedIDList():
                    if v in formal and v not in arr:
                        arr[v] = now
                n_log.append((now, counts_now()))
                if len(n_log) > 1200:
                    del n_log[:len(n_log) - 1200]
                pending_decide = None
                if trans is None and seg is None and (pend is None) and (not ended):
                    target = P[0] if all((v == 0.0 for v in last_ge.values())) else P[(P.index(last_phase[0]) + 1) % len(P)]
                    last_phase[0] = target
                    seg = {'ph': target, 's': now, 'G': cfg['g_min']}
                    last_ge[target] = now
                    trans = (now, 'g', target)
                    continue
                while trans and now >= trans[0] - 1e-09:
                    (tt, kind, ph) = trans
                    if kind == 'decide':
                        pending_decide = tt
                        break
                    elif kind == 'y':
                        cur_state = state_str(links, n_links, 'y', ph)
                        conn.trafficlight.setRedYellowGreenState(cfg['tls'], cur_state)
                        trans = (tt + cfg['yellow'][ph], 'ar', ph)
                    elif kind == 'ar':
                        cur_state = 'r' * n_links
                        conn.trafficlight.setRedYellowGreenState(cfg['tls'], cur_state)
                        tau = tt + cfg['all_red'][pend[1] if pend else ph]
                        if pend:
                            (ps, pph) = pend
                            pend = None
                            seg = {'ph': pph, 's': max(ps, tau), 'G': cfg['g_min']}
                            last_ge[pph] = max(ps, tau)
                            trans = (max(ps, tau), 'g', pph)
                        else:
                            trans = None
                            break
                    elif kind == 'g':
                        cur_state = state_str(links, n_links, 'G', ph)
                        conn.trafficlight.setRedYellowGreenState(cfg['tls'], cur_state)
                        trans = (seg['s'] + seg['G'] - TAIL, 'decide', ph)
                        sched_decide(trans[0])
                if fail:
                    break
                while cap_sched and now >= cap_sched[0] - 0.05:
                    cap = cap_sched.pop(0)
                    scene.write_signal(cur_state)
                    scene.sync_vehicles(conn, conn.vehicle.getIDList(), appearances, turn_by_vehicle)
                    (_, comp) = raw_capture(scene)
                    if comp.shape[:2] != (720, 1280):
                        comp = cv2.resize(comp, (1280, 720), interpolation=cv2.INTER_AREA)
                    jpg = cv2.imencode('.jpg', comp, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
                    if now >= 120 and not preview_saved:
                        (out_json.parent / f'{TAG}-camera.jpg').write_bytes(jpg)
                        preview_saved = True
                    cap_mem[cap] = jpg
                    for k in list(cap_mem):
                        if k < now - 6.0:
                            del cap_mem[k]
                    n_saved += 1
                if pending_decide is not None:
                    tt = pending_decide
                    e_ = tt - seg['s']
                    red_age = {q: 0.0 if q == seg['ph'] else now - last_ge.get(q, 0.0) for q in P}
                    interlock = None
                    (S_il, _) = legal_ns(seg['ph'], seg['G'], red_age, cfg)
                    for q in sorted(S_il, key=lambda q: -red_age.get(q, 0)) if not args.no_interlock else []:
                        (y_, r_) = (cfg['yellow'][q], cfg['all_red'][q])
                        if red_age.get(q, 0) + 10 * TAIL + y_ + r_ + cfg['g_min'] > R_MAX + seg['G']:
                            interlock = ('switch', q)
                            break
                    if interlock is not None:
                        (dec, ms) = (interlock, 0.0)
                        n_interlock += 1
                        dec_log.append((round(tt, 1), dec, 0, 'interlock'))
                    else:
                        (dec, ms) = infer_decide(round(tt, 1), seg['ph'], seg['G'], e_, red_age)
                        dec_log.append((round(tt, 1), dec, round(ms), 'model'))
                    if dec is None:
                        fail = f'decide-empty@{now:.0f}'
                        break
                    if dec == 'extend':
                        delta = min(EXT, cfg['g_max'] - seg['G'])
                        seg['G'] += delta
                        last_ge[seg['ph']] = seg['s'] + seg['G']
                        trans = (seg['s'] + seg['G'] - TAIL, 'decide', seg['ph'])
                        sched_decide(trans[0])
                    else:
                        (y, r) = (cfg['yellow'][seg['ph']], cfg['all_red'][dec[1]])
                        pend = (trans[0] + TAIL + y + r, dec[1])
                        trans = (trans[0] + TAIL, 'y', seg['ph'])
                        seg = None
                if now >= H_OFFICIAL - 1e-09 or ended or len(arr) >= N:
                    break
    finally:
        _close()
    J_H = None
    if fail is None and N:
        J_H = round(sum((min(arr.get(v, H_OFFICIAL), H_OFFICIAL) - planned[v] for v in formal)) / N, 2)
    mss = [m for (_, _, m, _) in dec_log if m]
    evaluation.write(out_json.parent / f'{TAG}-metrics.json', tripinfo, planned, fail)
    out_json.write_text(json.dumps({'tag': TAG, 'J_H': J_H, 'fail': fail, 'n_dec': len(dec_log), 'n_interlock': n_interlock, 'infer_fail': n_fail_infer, 'infer_ms_mean': round(sum(mss) / len(mss)) if mss else None, 'arrived': len(arr), 'N': N, 'frames': n_saved, 'wall_seconds': round(time.monotonic() - t_wall, 1)}, indent=1))
    print(out_json.read_text(), flush=True)
    os._exit(0)
if __name__ == '__main__':
    main()

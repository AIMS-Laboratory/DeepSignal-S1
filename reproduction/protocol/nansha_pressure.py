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
import argparse, atexit, base64, json, os, sys, time, urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT = Path.cwd()
TAG0 = next((a for a in sys.argv[1:] if not a.startswith('-')), None)
if TAG0 is None:
    raise SystemExit('用法: ns_mp_eval.py <tag> [--yolo URL] [--out DIR]')
os.environ['DEEPSIGNAL_JUNCTION_PROFILE'] = str(ROOT / f"configs/junctions/nansha-{TAG0.split('-')[0].lower()}-v2.json")
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts/carla'))
sys.path.insert(0, str(ROOT / 'protocol'))
import traci
import cv2
from run_ue5_control import UE5Scene, connect_ue5
from nansha_rules import load_ns, legal_ns, TAIL, EXT, R_MAX
from network_routes import probe_links, state_str, _imports
from deepsignal.demand_plan import PlannedArrivals
from deepsignal.observation import carla_image_to_bgr, compose_tiled_frame
from deepsignal.cameras import covers_of
STEP = 0.1
H_OFFICIAL = 1298.0
HYST_BIAS = 1.0
SMOOTH_W = (0.25, 0.25, 0.5)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--yolo', default='http://127.0.0.1:8031/v1/detect2')
    ap.add_argument('--out', default='protocol/ns_mp_eval')
    args = ap.parse_args()
    TAG = args.tag
    JUN = TAG.split('-')[0]
    cfg = load_ns(JUN)
    guides = json.loads((ROOT / f'protocol/lane-guides-ns/{JUN}.json').read_text())
    MOVES = {p: [f'{ap}-{kind}' for (ap, kind) in cfg['movements'][p]] for p in cfg['phases']}
    out_json = Path(args.out) / f'{TAG}.json'
    out_json.parent.mkdir(parents=True, exist_ok=True)
    if out_json.exists():
        raise SystemExit(f'{out_json} 已存在')
    work_dir = Path(args.out) / 'frames' / TAG
    work_dir.mkdir(parents=True, exist_ok=True)
    plan_dir = next((ROOT / f'out/nansha/plans-sft-final' / TAG for _ in [0]))
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
    world = client.get_world()
    stray = list(world.get_actors().filter('vehicle.*')) + list(world.get_actors().filter('sensor.*')) + [a for a in world.get_actors() if 'nanshasignal' in a.type_id]
    if stray:
        for a in stray:
            try:
                a.destroy()
            except RuntimeError:
                pass
        world.tick()
    label = f'nsmp-{TAG}'[:50]
    traci.start(['sumo', '--net-file', str(cfg['net']), '--route-files', str(routes), '--step-length', str(STEP), '--time-to-teleport', '-1', '--no-step-log', 'true', '--seed', str(plan.seed)], label=label)
    conn = traci.getConnection(label)

    def _close():
        try:
            conn.close()
        except Exception:
            pass
    atexit.register(_close)
    vh_meta = {v.vehicle_id: (v.approach, 'SR' if v.turn in ('s', 'r') else 'L') for v in plan.vehicles}
    rng = __import__('random').Random(plan.seed)
    palette = ('35,75,150', '150,35,35', '210,210,210', '40,40,40', '200,150,45')
    appearances = {v.vehicle_id: rng.choice(palette) for v in plan.vehicles}
    turn_by_vehicle = {v.vehicle_id: v.turn for v in plan.vehicles}
    P = cfg['phases']
    arr = {}
    last_ge = {q: 0.0 for q in P}
    seg = trans = pend = None
    last_phase = [P[0]]
    ended = False
    fail = None
    dec_log = []
    yolo_ms = []
    cap_sched = []
    cap_mem = {}
    t_wall = time.monotonic()
    preview_saved = False
    camera_cfg = ROOT / f'data/NanshaTrafficProject/outputs/nansha-twin/control/data/cameras/{JUN}.json'

    def raw_capture(scene):
        frame_id = scene.world.tick(20)
        frames = {}
        for (name, pending) in scene.queues.items():
            while True:
                frame = pending.get(timeout=20)
                if frame.frame == frame_id:
                    frames[name] = carla_image_to_bgr(frame)
                    break
        return (frame_id, _deg(compose_tiled_frame(frames, scene.rig, draw_labels=False)))

    def mp_decide(tt, cur, G, red_age, tiles):
        snaps = {}
        for dt in (4.0, 2.0, 0.0):
            want = round(tt - dt, 1)
            hit = cap_mem.get(want)
            if hit is None:
                raise RuntimeError(f'{TAG}@{tt:g} 决策窗缺帧 t{want:g}')
            (tw0, th0) = next(iter(tiles.values()))[2:4]
            payload = json.dumps({'image': base64.b64encode(hit).decode(), 'tiles': {ap: [x, y] for (ap, (x, y, w, h)) in tiles.items()}, 'tile_w': tw0, 'tile_h': th0, 'guides': guides}).encode()
            req = urllib.request.Request(args.yolo, data=payload, headers={'Content-Type': 'application/json'})
            t0 = time.monotonic()
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            yolo_ms.append((time.monotonic() - t0) * 1000)
            snaps[dt] = d['movement_calib']
        smooth = {m: sum((w * snaps[dt].get(m, 0.0) for (dt, w) in zip((4.0, 2.0, 0.0), SMOOTH_W))) for m in {m for mv in MOVES.values() for m in mv}}
        score = {p: sum((smooth.get(m, 0.0) for m in MOVES[p])) for p in P}
        (S_il, E_ok) = legal_ns(cur, G, red_age, cfg)
        cands = list(S_il) + ([cur] if E_ok else [])
        if not cands:
            return None
        want = max(cands, key=lambda p: (score[p] + (HYST_BIAS if p == cur else 0.0), red_age.get(p, 0.0), -P.index(p)))
        return 'extend' if want == cur else ('switch', want)

    def sched_decide(T):
        cap_sched.extend([round(T - 4.0, 1), round(T - 2.0, 1), round(T, 1)])
    try:
        with UE5Scene(client, cfg['net'], work_dir, camera_config=camera_cfg) as scene:
            if _NS_J8:
                import carla as _carla
                import random as _random
                _jr = _random.Random(int(plan.seed))
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
            scene.sumo_connection = conn
            from deepsignal.cameras import slot_offsets
            (tw, th) = (scene.rig.tile_width, scene.rig.tile_height)
            offs = slot_offsets(scene.rig)
            tiles = {}
            for cam in scene.cameras:
                for ap in covers_of(scene.rig, cam):
                    (ox, oy) = offs[ap] if ap in offs else offs[cam]
                    tiles[ap] = (ox, oy, tw, th)
            missing = {a for a in guides} - set(tiles)
            if missing:
                raise RuntimeError(f'tile 映射缺进口 {missing}（cameras={list(scene.cameras)}）')
            cur_state = 'r' * n_links
            conn.trafficlight.setRedYellowGreenState(cfg['tls'], cur_state)
            while True:
                conn.simulationStep()
                now = conn.simulation.getTime()
                for v in conn.simulation.getArrivedIDList():
                    if v in formal and v not in arr:
                        arr[v] = now
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
                while cap_sched and now >= cap_sched[0] - 0.05:
                    cap = cap_sched.pop(0)
                    scene.write_signal(cur_state)
                    scene.sync_vehicles(conn, conn.vehicle.getIDList(), appearances, turn_by_vehicle)
                    (_, comp) = raw_capture(scene)
                    jpg = cv2.imencode('.jpg', comp, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
                    if now >= 120 and not preview_saved:
                        (out_json.parent / f'{TAG}-camera.jpg').write_bytes(jpg)
                        preview_saved = True
                    cap_mem[cap] = jpg
                    for k in list(cap_mem):
                        if k < now - 6.0:
                            del cap_mem[k]
                if pending_decide is not None:
                    tt = pending_decide
                    red_age = {q: 0.0 if q == seg['ph'] else now - last_ge.get(q, 0.0) for q in P}
                    interlock = None
                    (S_il, _) = legal_ns(seg['ph'], seg['G'], red_age, cfg)
                    for q in sorted(S_il, key=lambda q: -red_age.get(q, 0)):
                        (y_, r_) = (cfg['yellow'][q], cfg['all_red'][q])
                        if red_age.get(q, 0) + 10 * TAIL + y_ + r_ + cfg['g_min'] > R_MAX + seg['G']:
                            interlock = ('switch', q)
                            break
                    if interlock is not None:
                        dec = interlock
                    else:
                        dec = mp_decide(round(tt, 1), seg['ph'], seg['G'], red_age, tiles)
                    dec_log.append((round(tt, 1), dec))
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
    mss = yolo_ms or [0]
    out_json.write_text(json.dumps({'tag': TAG, 'J_H': J_H, 'fail': fail, 'n_dec': len(dec_log), 'yolo_ms_mean': round(sum(yolo_ms) / len(mss), 1), 'wall_seconds': round(time.monotonic() - t_wall, 1)}, indent=1))
    print(f'{TAG}: J_H={J_H} fail={fail} 决策 {len(dec_log)} yolo均值 {sum(mss) / len(mss):.0f}ms {time.monotonic() - t_wall:.0f}s', flush=True)
    os._exit(0)
if __name__ == '__main__':
    main()

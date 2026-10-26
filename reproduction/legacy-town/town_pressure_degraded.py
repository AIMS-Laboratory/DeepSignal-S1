import base64, json, os, queue as queue_mod, sys, time, urllib.request
from collections import deque
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path.cwd()
sys.path.insert(0, 'scripts/carla')
sys.path.insert(0, 'protocol')
sys.path.insert(0, 'protocol')
sys.path.insert(0, 'protocol')
import carla
import cv2
import numpy as np
import sumo_fork_probe as sfp
from sumo_fork_probe import adaptive_controller, start_sumo, table_answer
from deepsignal.decision_loop import FinalAnswer
from deepsignal.runtime import CarlaSession, clear_idle_watchdog_flag
from deepsignal.cameras import load_camera_rig_config, mount_forward_cameras
from deepsignal.cosimulation import sumo_to_carla_transform
from deepsignal.spatial import actor_front_offset
from deepsignal.ue4_junction import TARGET_JUNCTION_ID, JunctionSignalMirror, mount_junction_markings
from deepsignal.observation import carla_image_to_bgr, compose_tiled_frame
from episode_settings import make_raw, NET, TABLE_GREEN
from signal_states import PHASES, warm_states, harvest
from town_rules import T_END, legal_b
YOLO_URL = os.environ.get('YOLO_URL', 'http://localhost:8030/v1/detect2')
YOLO_TILES = {'E': [0, 0], 'W': [640, 0], 'S': [0, 360], 'N': [640, 360]}
GUIDES = json.loads((ROOT / 'protocol/lane-guides-town.json').read_text())
MOVES = {'ew_straight': ('E-SR', 'W-SR'), 'ew_left': ('E-L', 'W-L'), 'ns_straight': ('S-SR', 'N-SR'), 'ns_left': ('S-L', 'N-L')}
ALL_MOVES = [f'{d}-{k}' for d in 'EWSN' for k in ('SR', 'L')]
HYST_BIAS = 1.0

def yolo_movement(jpeg_bytes):
    payload = json.dumps({'image': base64.b64encode(jpeg_bytes).decode(), 'tiles': YOLO_TILES, 'guides': GUIDES}).encode()
    req = urllib.request.Request(YOLO_URL, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return d['movement_calib']

def decide_mp_v2(hist3, cur, G, red_age, bias=HYST_BIAS):
    smooth = {m: 0.25 * h[0] + 0.25 * h[1] + 0.5 * h[2] for (m, h) in hist3.items()}
    score = {p: sum((smooth.get(m, 0.0) for m in MOVES[p])) for p in PHASES}
    (S, E) = legal_b(cur, G, red_age)
    cands = list(S) + ([cur] if E else [])
    if not cands:
        return None
    want = max(cands, key=lambda p: (score[p] + (bias if p == cur else 0.0), red_age.get(p, 0.0), -PHASES.index(p)))
    return 'extend' if want == cur else ('switch', want)

def main():
    tag = sys.argv[1]
    (cond, seed_s) = tag.rsplit('-', 1)
    raw = make_raw(cond, int(seed_s))
    routes = Path(f'out/s1-e0/plans/nc-{tag}/routes.rou.xml')
    OUTD = os.environ.get('OUTD', 'protocol/b_mp_v2')
    DEG = os.environ.get('DEG', 'none')
    DEGP = float(os.environ.get('DEGP', '9'))
    out_json = Path(OUTD) / f'{tag}.json'
    out_json.parent.mkdir(exist_ok=True)
    if out_json.exists():
        raise SystemExit(f'{out_json} 已存在')
    if DEG == 'mb':
        _k = np.zeros((1, int(DEGP)), dtype=np.float32)
        _k[0, :] = 1.0 / int(DEGP)

        def _deg(img):
            return cv2.filter2D(img, -1, _k)
    elif DEG == 'df':

        def _deg(img):
            return cv2.GaussianBlur(img, (0, 0), DEGP)
    else:

        def _deg(img):
            return img
    planned = {v['vehicle_id']: v['planned_depart'] for v in json.loads(Path(f'out/s1-e0/plans/nc-{tag}/plan.json').read_text())['vehicles'] if v['cohort'] == 'formal'}
    formal_set = set(planned)
    clear_idle_watchdog_flag()
    client = carla.Client('127.0.0.1', int(os.environ.get('CARLA_RPC_PORT', '2000')))
    client.set_timeout(30)
    world = client.get_world()
    if (client.get_client_version(), client.get_server_version()) != ('0.9.16', '0.9.16'):
        raise RuntimeError('本运行仅验收 CARLA 0.9.16')
    if world.get_actors().filter('vehicle.*') or world.get_actors().filter('sensor.*'):
        world.tick()
        for actor in list(world.get_actors().filter('vehicle.*')) + list(world.get_actors().filter('sensor.*')):
            try:
                actor.destroy()
            except RuntimeError:
                pass
        world.tick()
        if world.get_actors().filter('vehicle.*') or world.get_actors().filter('sensor.*'):
            raise RuntimeError('世界残留清理失败')
    root_xml = ET.parse(NET).getroot()
    offs = [float(v) for v in root_xml.find('location').attrib['netOffset'].split(',')]
    net_offset = (offs[0], offs[1])
    warm_states()
    vehicle_actors = {}
    arr = {}
    t_wall = time.monotonic()
    preview_saved = False
    yolo_ms = []
    session = None
    conn = None
    frame_buf = deque(maxlen=70)
    n_dec = [0]
    n_switch = [0]
    fail = [None]
    J = [None]
    try:
        with CarlaSession(world, float(raw['step']), client=client) as session:
            original = [(l, l.get_state(), l.is_frozen()) for l in world.get_actors().filter('traffic.traffic_light')]
            session.register_cleanup(lambda : [l.set_state(s) or l.freeze(f) for (l, s, f) in original])

            def clear_vehicles():
                for actor in list(vehicle_actors.values()):
                    try:
                        actor.destroy()
                    except RuntimeError:
                        pass
                vehicle_actors.clear()
            session.register_cleanup(clear_vehicles)
            for (light, _, _) in original:
                light.freeze(True)
                light.set_state(carla.TrafficLightState.Red)
            from deepsignal.junction_sim import resolve_channels
            (channels, _) = resolve_channels(world, NET)
            signal_mirror = JunctionSignalMirror(channels)
            mount_junction_markings(world, client, session, NET)
            camera_config = load_camera_rig_config(ROOT / 'configs/cameras.town10hd.json')

            def register_camera(camera):
                session.register_actor(camera, stop_before_destroy=True)
                return camera
            junction_lights = list(world.get_traffic_lights_in_junction(TARGET_JUNCTION_ID))
            cameras = mount_forward_cameras(world, junction_lights, camera_config, register_actor=register_camera)
            queues = {name: queue_mod.Queue() for name in cameras}
            for (name, camera) in cameras.items():
                camera.listen(queues[name].put)

            def snap(frames):
                img = compose_tiled_frame(frames, camera_config, draw_labels=False)
                return cv2.imencode('.jpg', _deg(img), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()

            def capture():
                frame_id = world.tick()
                frames = {}
                for (name, q) in queues.items():
                    while True:
                        frame = q.get(timeout=20)
                        if frame.frame == frame_id:
                            frames[name] = carla_image_to_bgr(frame)
                            break
                return (frame_id, frames)
            for _ in range(15):
                capture()
            conn = start_sumo(NET, routes, raw, Path('protocol/b_mp_v2') / f'tripinfo-{tag}.xml', f'bmp2-{tag}')
            c = adaptive_controller(raw, NET, TABLE_GREEN)
            update = c.current_update(0.0)
            from signal_states import STATES
            set_st = lambda key: conn.trafficlight.setRedYellowGreenState(str(sfp.TARGET_TLS_ID), STATES[key])

            def hist3_v2(tt):
                snaps = {}
                for dt in (4.0, 2.0, 0.0):
                    want = round(tt - dt, 1)
                    hit = next((b for (t, b) in frame_buf if abs(t - want) < (0.15 if dt == 0.0 else 0.05)), None)
                    if hit is None:
                        raise RuntimeError(f'{tag}@{tt:g} 缓存缺帧 t{want:g}')
                    t0 = time.monotonic()
                    mv = yolo_movement(hit)
                    yolo_ms.append((time.monotonic() - t0) * 1000)
                    snaps[dt] = mv
                return {m: (snaps[4.0].get(m, 0.0), snaps[2.0].get(m, 0.0), snaps[0.0].get(m, 0.0)) for m in ALL_MOVES}

            def mp_decide(tt, cur, G, red_age):
                dec = decide_mp_v2(hist3_v2(tt), cur, G, red_age)
                n_dec[0] += 1
                if isinstance(dec, tuple):
                    n_switch[0] += 1
                return dec
            (green_start, green_end, stage_of) = ({}, {}, {})
            stage = 'pre'
            trans = None
            pend = None
            seg = None
            ended = False
            last_ge = {}

            def mirror():
                signal_mirror.write(conn.trafficlight.getRedYellowGreenState(str(sfp.TARGET_TLS_ID)))
                active = set(conn.vehicle.getIDList())
                for vid in sorted(active):
                    if vid not in vehicle_actors:
                        bp = world.get_blueprint_library().find('vehicle.tesla.model3')
                        bp.set_attribute('role_name', 'mp2_rec')
                        bp.set_attribute('color', {'s': '30,110,210', 'r': '220,180,30', 'l': '180,40,40'}[vid.split('-')[1]])
                        actor = world.try_spawn_actor(bp, sumo_to_carla_transform(conn.vehicle.getPosition3D(vid), conn.vehicle.getAngle(vid), net_offset, half_length=2.25))
                        if actor is None:
                            continue
                        vehicle_actors[vid] = actor
                        actor.set_simulate_physics(False)
                    vehicle_actors[vid].set_transform(sumo_to_carla_transform(conn.vehicle.getPosition3D(vid), conn.vehicle.getAngle(vid), net_offset, half_length=actor_front_offset(vehicle_actors[vid])))
                for vid in set(vehicle_actors) - active:
                    vehicle_actors.pop(vid).destroy()
            while True:
                if stage == 'pre':
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
                    boundary = False
                    for e in c.tick(now, status=status, window={'frame_times': (now,), 'signal_history': ()}):
                        if isinstance(e, sfp.SignalUpdate):
                            if e.group:
                                if e.stage == e.group:
                                    if stage_of.get(e.group) != 'g':
                                        green_start[e.group] = e.time
                                    stage_of[e.group] = 'g'
                                elif e.stage == f'{e.group}_countdown' and stage_of.get(e.group) != 'cd':
                                    stage_of[e.group] = 'cd'
                                    green_end[e.group] = e.time + 5.0
                                    boundary = True
                            harvest(e)
                            update = e
                    if boundary and stage == 'pre':
                        stage = 'auto'
                        cur0 = max(green_end, key=lambda q: green_end[q])
                        gs0 = green_start.get(cur0, now)
                        e0 = now - gs0
                        gc0 = green_end[cur0] - gs0
                        red_age = {q: 0.0 if q == cur0 else now - green_end.get(q, 0.0) for q in PHASES}
                        hist0 = {m: (0.0, 0.0, 0.0) for m in ALL_MOVES}
                        dec = decide_mp_v2(hist0, cur0, gc0, red_age)
                        n_dec[0] += 1
                        if dec is None:
                            fail[0] = 'handoff-empty'
                            break
                        last_ge = {q: green_end[q] for q in green_end}
                        if dec == 'extend':
                            G1 = gc0 + min(5.0, 60.0 - gc0)
                            seg = {'ph': cur0, 's': gs0, 'G': G1}
                            last_ge[cur0] = gs0 + G1
                            trans = (gs0 + G1 - 5.0, 'decide', cur0)
                        else:
                            last_ge[cur0] = now + 5.0
                            seg = None
                            trans = (now + 5.0, 'y', cur0)
                            pend = (now + 10.0, dec[1])
                    mirror()
                    (_, frames) = capture()
                    frame_buf.append((round(now, 1), snap(frames)))
                    continue
                conn.simulationStep()
                now = conn.simulation.getTime()
                for v in conn.simulation.getArrivedIDList():
                    if v in formal_set and v not in arr:
                        arr[v] = now
                while trans and now >= trans[0] - 1e-09:
                    (tt, kind, ph) = trans
                    if kind == 'decide':
                        e_ = tt - seg['s']
                        red_age = {q: 0.0 if q == seg['ph'] else now - last_ge.get(q, 0.0) for q in PHASES}
                        dec = mp_decide(tt, seg['ph'], seg['G'], red_age)
                        if dec is None:
                            fail[0] = f'decide-empty@{now:.0f}'
                            break
                        if dec == 'extend':
                            delta = min(5.0, 60.0 - seg['G'])
                            seg['G'] += delta
                            last_ge[seg['ph']] = seg['s'] + seg['G']
                            trans = (seg['s'] + seg['G'] - 5.0, 'decide', seg['ph'])
                        else:
                            pend = (trans[0] + 5.0, dec[1])
                            trans = (tt, 'y', seg['ph'])
                            seg = None
                    elif kind == 'y':
                        set_st((ph, 'y'))
                        trans = (tt + 3.0, 'ar', ph)
                    elif kind == 'ar':
                        set_st(('all_red', 'r'))
                        tau = tt + 2.0
                        if tau > T_END:
                            trans = None
                            ended = True
                            break
                        if pend:
                            (ps, pph) = pend
                            pend = None
                            seg = {'ph': pph, 's': max(ps, tau), 'G': 6.0}
                            last_ge[pph] = max(ps, tau)
                            trans = (max(ps, tau), 'g', pph)
                        else:
                            trans = None
                            break
                    elif kind == 'g':
                        set_st((ph, 'G'))
                        trans = (tt + 1.0, 'decide', ph)
                if fail[0]:
                    break
                mirror()
                (_, frames) = capture()
                frame_buf.append((round(now, 1), snap(frames)))
                if now >= 120 and not preview_saved:
                    (out_json.parent / f'{tag}-camera.jpg').write_bytes(frame_buf[-1][1])
                    preview_saved = True
                if now >= T_END - 1e-09 or ended:
                    break
                if not ended and trans is None and (pend is None) and (seg is None):
                    red_age = {q: now - last_ge.get(q, 0.0) for q in PHASES}
                    dec = mp_decide(now, max(red_age, key=lambda q: red_age[q]), 60.0, red_age)
                    if dec is None or dec == 'extend':
                        fail[0] = 'fallback-empty'
                        break
                    seg = {'ph': dec[1], 's': now, 'G': 6.0}
                    last_ge[dec[1]] = now
                    trans = (now, 'g', dec[1])
    finally:
        if conn is not None:
            conn.close()
        try:
            if session is not None:
                session._destroy_actors()
        except Exception:
            pass
        world.wait_for_tick(20)
    if fail[0] is None:
        J[0] = round(sum((min(arr.get(v, T_END), T_END) - d for (v, d) in planned.items() if d < T_END)), 1)
    out_json.write_text(json.dumps({'tag': tag, 'J': J[0], 'n_dec': n_dec[0], 'n_switch': n_switch[0], 'fail': fail[0], 'yolo_ms_mean': round(sum(yolo_ms) / len(yolo_ms), 1) if yolo_ms else None, 'wall_seconds': round(time.monotonic() - t_wall, 1)}, indent=1))
    print(f'{tag}: J={J[0]} n_dec={n_dec[0]} sw={n_switch[0]} fail={fail[0]} yolo_mean={(sum(yolo_ms) / len(yolo_ms) if yolo_ms else 0):.0f}ms {time.monotonic() - t_wall:.0f}s', flush=True)
if __name__ == '__main__':
    main()

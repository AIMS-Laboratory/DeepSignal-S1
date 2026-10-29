import argparse, base64, json, os, queue as queue_mod, sys, time, urllib.request
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
from intersection_metrics import IntersectionMetrics
from deepsignal.cosimulation import sumo_to_carla_transform
from deepsignal.spatial import actor_front_offset
from deepsignal.ue4_junction import TARGET_JUNCTION_ID, JunctionSignalMirror, mount_junction_markings
from deepsignal.observation import carla_image_to_bgr, compose_tiled_frame
from episode_settings import make_raw, NET, TABLE_GREEN
from signal_states import PHASES, warm_states, harvest
from town_rules import T_END, legal_b
from visual_perturbation import VisualPerturbation
from evaluation_trace import SignalTrace

def build_state(cur, G, e, red_age):
    legal = (['extend_5s'] if legal_b(cur, G, red_age)[1] else []) + [f'switch_to_{p}' for p in PHASES if p in legal_b(cur, G, red_age)[0]]
    from traffic_context import PHASE_DESC, STATE_TASK
    return ({'task': STATE_TASK, 'intersection_layout': {'phases': PHASE_DESC, 'approaches': 'Four approaches (E/W/S/N), each with a through+right lane and a left-turn lane.', 'camera_view': 'Tiled 1280x720 frame from four cameras, one per approach.'}, 'signal': {'current_phase': cur, 'green_elapsed_s': round(e, 1), 'committed_total_green_s': round(G, 1)}, 'legal_actions': legal}, legal)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--serve', default='http://127.0.0.1:8040')
    ap.add_argument('--out', default='protocol/b_s1_j')
    ap.add_argument('--jitter', type=float, default=8.0, help='外参扰动幅度（度）：yaw/pitch ±jitter、roll ±jitter/2，整回合静态')
    ap.add_argument('--degrade', choices=('none', 'mb', 'df'), default='none', help='在线退化：mb=水平线性运动模糊(核长 px)、df=高斯失焦(σ)；整回合静态，捕获后推理前（Q4 双臂同参）')
    ap.add_argument('--deg-param', type=float, default=9.0)
    args = ap.parse_args()
    if args.degrade == 'mb':
        _k = np.zeros((1, int(args.deg_param)), dtype=np.float32)
        _k[0, :] = 1.0 / int(args.deg_param)

        def _deg(img):
            return cv2.filter2D(img, -1, _k)
    elif args.degrade == 'df':

        def _deg(img):
            return cv2.GaussianBlur(img, (0, 0), float(args.deg_param))
    else:

        def _deg(img):
            return img
    tag = args.tag
    base = tag
    suf = tag.rsplit('-', 1)[-1]
    if suf.startswith('j') and suf[1:].isdigit():
        base = tag.rsplit('-', 1)[0]
    out_json = Path(args.out) / f'{tag}.json'
    out_json.parent.mkdir(exist_ok=True)
    if out_json.exists():
        raise SystemExit(f'{out_json} 已存在')
    (cond, seed_s) = base.rsplit('-', 1)
    visual = VisualPerturbation.from_env(int(seed_s))
    raw = make_raw(cond, int(seed_s))
    routes = Path(f'out/s1-e0/plans/nc-{base}/routes.rou.xml')
    planned = {v['vehicle_id']: v['planned_depart'] for v in json.loads(Path(f'out/s1-e0/plans/nc-{base}/plan.json').read_text())['vehicles'] if v['cohort'] == 'formal'}
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
    dec_log = []
    t_wall = time.monotonic()
    preview_saved = False
    session = None
    conn = None
    frame_buf = deque(maxlen=70)
    n_fail_infer = [0]
    fail = [None]
    J = [None]
    signal_trace = SignalTrace()

    def infer_decide(tt, cur, G, e, red_age):
        (state, legal) = build_state(cur, G, e, red_age)
        if not legal:
            return None
        frames_b64 = []
        for dt in (4.0, 2.0, 0.0):
            want = round(tt - dt, 1)
            hit = next((b for (t, b) in frame_buf if abs(t - want) < (0.15 if dt == 0.0 else 0.05)), None)
            if hit is None:
                raise RuntimeError(f'{tag}@{tt:g} 缓存缺帧 t{want:g}')
            frames_b64.append(base64.b64encode(hit).decode())
        t0 = time.monotonic()
        req = urllib.request.Request(f'{args.serve}/v1/decide', data=json.dumps({'state': state, 'frames': frames_b64}).encode(), headers={'Content-Type': 'application/json'})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=180).read())
        except Exception:
            n_fail_infer[0] += 1
            return (None, 0.0)
        ms = (time.monotonic() - t0) * 1000
        choice = r.get('choice', '')
        if not choice or r.get('error'):
            n_fail_infer[0] += 1
            return (None, ms)
        if choice == 'extend_5s':
            return ('extend', ms)
        if choice.startswith('switch_to_'):
            p = choice.removeprefix('switch_to_')
            if p in legal_b(cur, G, red_age)[0]:
                return (('switch', p), ms)
        return (None, ms)
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
            if args.jitter > 0:
                # Read the mounted poses only after UE5 has published the new actors.
                world.tick()
                import random as _rnd
                jr = _rnd.Random(int(seed_s) + int(args.jitter * 10))
                for (name, camera) in cameras.items():
                    t = camera.get_transform()
                    (dy, dp, dr) = (jr.uniform(-args.jitter, args.jitter), jr.uniform(-args.jitter, args.jitter), jr.uniform(-args.jitter / 2, args.jitter / 2))
                    t.rotation.yaw += dy
                    t.rotation.pitch += dp
                    t.rotation.roll += dr
                    camera.set_transform(t)
                    print(f'[jitter] {name}: yaw{dy:+.1f} pitch{dp:+.1f} roll{dr:+.1f}', flush=True)
            if 'visual' in locals():
                if visual.condition in ('angle15', 'shake5') and args.jitter <= 0:
                    world.tick()
                visual.bind(cameras)
            queues = {name: queue_mod.Queue() for name in cameras}
            for (name, camera) in cameras.items():
                camera.listen(queues[name].put)

            def snap(frames):
                img = compose_tiled_frame(frames, camera_config, draw_labels=False)
                return cv2.imencode('.jpg', visual.image(_deg(img)), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()

            def capture():
                visual.move(conn.simulation.getTime() if conn is not None else 0.0)
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
            conn = start_sumo(NET, routes, raw, Path(args.out) / f'tripinfo-{tag}.xml', f'bs1-{tag}')
            evaluation = IntersectionMetrics(conn, sfp.TARGET_TLS_ID)
            c = adaptive_controller(raw, NET, TABLE_GREEN)
            update = c.current_update(0.0)
            from signal_states import STATES
            def set_st(key):
                conn.trafficlight.setRedYellowGreenState(str(sfp.TARGET_TLS_ID), STATES[key])
                signal_trace.stage(conn.simulation.getTime(), *key)
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
                        bp.set_attribute('role_name', 's1_rec')
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
                    evaluation.update(now)
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
                        (dec, ms) = infer_decide(now, cur0, gc0, e0, red_age)
                        dec_log.append((round(now, 1), dec, round(ms)))
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
                            if 'signal_trace' in locals():
                                signal_trace.switch(now, cur0, dec[1])
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
                evaluation.update(now)
                for v in conn.simulation.getArrivedIDList():
                    if v in formal_set and v not in arr:
                        arr[v] = now
                while trans and now >= trans[0] - 1e-09:
                    (tt, kind, ph) = trans
                    if kind == 'decide':
                        e_ = tt - seg['s']
                        red_age = {q: 0.0 if q == seg['ph'] else now - last_ge.get(q, 0.0) for q in PHASES}
                        (dec, ms) = infer_decide(tt, seg['ph'], seg['G'], e_, red_age)
                        dec_log.append((round(tt, 1), dec, round(ms)))
                        if dec is None:
                            fail[0] = f'decide-empty@{now:.0f}'
                            break
                        if dec == 'extend':
                            delta = min(5.0, 60.0 - seg['G'])
                            seg['G'] += delta
                            last_ge[seg['ph']] = seg['s'] + seg['G']
                            trans = (seg['s'] + seg['G'] - 5.0, 'decide', seg['ph'])
                        else:
                            green_until = seg['s'] + seg['G']
                            if 'signal_trace' in locals():
                                signal_trace.switch(tt, seg['ph'], dec[1])
                            last_ge[seg['ph']] = green_until
                            pend = (green_until + 5.0, dec[1])
                            trans = (green_until, 'y', seg['ph'])
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
                if now >= T_END - 1e-09:
                    break
                if not ended and trans is None and (pend is None) and (seg is None):
                    red_age = {q: now - last_ge.get(q, 0.0) for q in PHASES}
                    (dec, ms) = infer_decide(now, max(red_age, key=lambda q: red_age[q]), 60.0, 1000000000.0, red_age)
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
    mss = [m for (_, _, m) in dec_log if m]
    evaluation.write(out_json.parent / f'{tag}-metrics.json', out_json.parent / f'tripinfo-{tag}.xml', planned, fail[0])
    out_json.write_text(json.dumps({'tag': tag, 'J': J[0], 'fail': fail[0], 'n_dec': len(dec_log), 'infer_fail': n_fail_infer[0], 'infer_ms_mean': round(sum(mss) / len(mss), 0) if mss else None, 'visual': visual.metadata(), 'signal_trace': signal_trace.metadata(T_END), 'wall_seconds': round(time.monotonic() - t_wall, 1)}, indent=1))
    print(out_json.read_text(), flush=True)
if __name__ == '__main__':
    main()

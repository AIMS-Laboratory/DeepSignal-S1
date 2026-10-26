from __future__ import annotations
import json
import math
from pathlib import Path
import queue
import sys
import time
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[2]
import carla
import cv2
import numpy as np
from deepsignal.cameras import CameraRigConfig, covers_of, load_camera_rig_config, mount_forward_cameras, slot_offsets
from deepsignal.cosimulation import sumo_to_carla_transform
from deepsignal.junction_profile import active_profile
from deepsignal.junction_sim import resolve_channels
from deepsignal.lane_guides import build_lane_guides, draw_lane_guides
from deepsignal.observation import carla_image_to_bgr, compose_tiled_frame
from deepsignal.runtime import CarlaSession
from deepsignal.spatial import actor_front_offset
from deepsignal.ue4_junction import JunctionSignalMirror, mount_junction_markings
from deepsignal.junction_profile import active_profile as _load_profile
profile = _load_profile()

def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def connect_ue5(port=2100):
    profile = active_profile()
    deadline = time.monotonic() + 90
    while True:
        try:
            client = carla.Client('127.0.0.1', port)
            client.set_timeout(5)
            world = client.get_world()
            if profile.map_name.startswith('Nansha'):
                world.get_actors()
            elif profile.map_name not in world.get_map().name:
                raise ValueError(f'UE5 must already be on {profile.map_name}')
            client.set_timeout(30)
            return client
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)

class UE5Scene:

    def __init__(self, client, net, output, camera_config=None, instance_labels=False, fixed_delta_seconds=0.1, lighting='noon'):
        (self.client, self.net, self.output) = (client, net, output)
        self.world = client.get_world()
        self.session = CarlaSession(self.world, fixed_delta_seconds, client=client)
        self.lighting_preset = carla.WeatherParameters.ClearSunset if lighting == 'sunset' else carla.WeatherParameters.ClearNoon
        self.vehicles = {}
        self.camera_spec_path = str(camera_config or ROOT / 'configs/cameras.town10hd.json')
        self.signal_visuals = None
        self.sumo_connection = None
        self.scene_origin = None
        self.photo_surface = None
        self.vehicle_boxes = {}
        if active_profile().map_name.startswith('Nansha'):
            twin = ROOT / 'data/NanshaTrafficProject/outputs/nansha-twin'
            self.scene_origin = json.loads((twin / 'data/coordinate_frame.json').read_text())['scene_origin_sumo_xy_m']
            sys.path.insert(0, str(twin / 'integration'))
            try:
                import photo_surface
                if photo_surface.active():
                    self.photo_surface = photo_surface
            except Exception:
                self.photo_surface = None
        if active_profile().map_name.startswith('Nansha'):
            self.rig = None
        else:
            self.rig = load_camera_rig_config(camera_config or ROOT / 'configs/cameras.town10hd.json')
        location = ET.parse(net).getroot().find('location')
        self.offset = tuple((float(v) for v in location.attrib['netOffset'].split(',')))
        self.original_lights = []
        self.instance_labels = instance_labels

    def __enter__(self):
        if self.world.get_actors().filter('vehicle.*') or self.world.get_actors().filter('sensor.*'):
            raise RuntimeError('UE5世界存在其他车辆或传感器，不能混入本轮回合')
        self.session.__enter__()
        try:
            self.weather = self.world.get_weather()
            self.world.set_weather(self.lighting_preset)
            for light in self.world.get_actors().filter('traffic.traffic_light'):
                self.original_lights.append((light, light.get_state(), light.is_frozen()))
                light.freeze(True)
                light.set_state(carla.TrafficLightState.Red)
            if profile.map_name.startswith('Nansha'):
                self.signal_visuals = None
                self.mirror = None
                cameras_spec = json.loads(Path(self.camera_spec_path).read_text(encoding='utf-8'))
                import itertools
                spec_cameras = cameras_spec['cameras']
                net_root = ET.parse(self.net).getroot()
                stops = {}
                for label in profile.approach_labels:
                    edge_node = net_root.find(f"edge[@id='{profile.approach_edges[label]}']")
                    lanes_with_shape = [ln for ln in edge_node.findall('lane') if 'shape' in ln.attrib]
                    if not lanes_with_shape:
                        raise RuntimeError(f'进口 {label} 的边无车道 shape，相机绑定失败')
                    lane0 = next((ln for ln in lanes_with_shape if ln.attrib['index'] == '0'), lanes_with_shape[0])
                    shape0 = [tuple(map(float, s.split(',')[:2])) for s in lane0.attrib['shape'].split()]
                    stop = shape0[-1]
                    stops[label] = np.array([stop[0] - self.scene_origin[0], -(stop[1] - self.scene_origin[1])])
                pole = np.array(spec_cameras[0]['location'][:2])
                labels = list(stops)
                vectors = {i: np.array([math.cos(math.radians(c['rotation']['yaw'])), math.sin(math.radians(c['rotation']['yaw']))]) for (i, c) in enumerate(spec_cameras)}
                binding = min(itertools.permutations(range(len(spec_cameras)), len(labels)), key=lambda perm: sum((-float(np.dot(vectors[i], stops[a] - pole) / np.linalg.norm(stops[a] - pole)) for (a, i) in zip(labels, perm))))
                blueprint = self.world.get_blueprint_library().find('sensor.camera.rgb')
                self.cameras = {}
                for (label, cam_index) in zip(labels, binding):
                    cam = spec_cameras[cam_index]
                    blueprint.set_attribute('image_size_x', str(cam['image_width']))
                    blueprint.set_attribute('image_size_y', str(cam['image_height']))
                    blueprint.set_attribute('fov', str(cam.get('fov', 90.0)))
                    (location, rotation) = (cam['location'], cam['rotation'])
                    actor = self.world.spawn_actor(blueprint, carla.Transform(carla.Location(x=location[0], y=location[1], z=location[2]), carla.Rotation(pitch=rotation['pitch'], yaw=rotation['yaw'], roll=rotation.get('roll', 0.0))))
                    self.session.register_actor(actor, stop_before_destroy=True)
                    self.cameras[label] = actor
                self.rig = CameraRigConfig(tile_width=spec_cameras[0]['analysis_width'], tile_height=spec_cameras[0]['analysis_height'], fov=spec_cameras[0].get('fov', 90.0))
                twin = ROOT / 'data/NanshaTrafficProject/outputs/nansha-twin'
                from signal_visuals import SignalVisuals
                self.signal_visuals = SignalVisuals(self.world, twin / 'nine', self.client)
                fallback = self.world.get_blueprint_library()
                for head in self.signal_visuals.heads:
                    shape = head['fixture']['shape']
                    head['blueprints'] = {state: fallback.find(f'static.prop.nanshasignal_{shape}_{state}') for state in ('red', 'yellow', 'green')}
                self.guides = {}
            else:
                (channels, mapping) = resolve_channels(self.world, self.net)
                self.mirror = JunctionSignalMirror(channels)
                write_json(self.output / 'signal-mapping.json', mapping)
                mount_junction_markings(self.world, self.client, self.session, self.net)
                self.cameras = mount_forward_cameras(self.world, list(self.world.get_traffic_lights_in_junction(profile.junction_id)), self.rig, register_actor=lambda actor: self.session.register_actor(actor, stop_before_destroy=True))
            covered = [a for cam in self.cameras for a in covers_of(self.rig, cam)]
            expected = sorted(profile.approach_labels if profile.map_name.startswith('Nansha') else ['E', 'N', 'S', 'W'])
            if sorted(set(covered)) != expected:
                raise RuntimeError(f'相机覆盖不完整: {sorted(set(covered))} != {expected}')
            self.queues = {name: queue.Queue() for name in self.cameras}
            for (name, camera) in self.cameras.items():
                camera.listen(self.queues[name].put)
            self.instance_queues = {}
            if self.instance_labels:
                for (name, camera) in self.cameras.items():
                    bp = self.world.get_blueprint_library().find('sensor.camera.instance_segmentation')
                    for key in ('image_size_x', 'image_size_y', 'fov'):
                        bp.set_attribute(key, camera.attributes[key])
                    sensor = self.world.spawn_actor(bp, carla.Transform(), attach_to=camera)
                    self.session.register_actor(sensor, stop_before_destroy=True)
                    self.instance_queues[name] = queue.Queue()
                    sensor.listen(self.instance_queues[name].put)
            for _ in range(15):
                self.capture()
            write_json(self.output / 'cameras.json', {name: {'location': [cam.get_transform().location.x, cam.get_transform().location.y, cam.get_transform().location.z], 'yaw': cam.get_transform().rotation.yaw, 'pitch': cam.get_transform().rotation.pitch} for (name, cam) in self.cameras.items()})
            self.guides = build_lane_guides(self.net, self.cameras, self.rig, scene_origin=self.scene_origin, photo_surface=self.photo_surface) if profile.map_name.startswith('Nansha') else build_lane_guides(self.net, self.cameras, self.rig)
            write_json(self.output / 'lane-guides.json', self.guides)
            return self
        except Exception:
            self.__exit__(*sys.exc_info())
            raise

    def camera_for(self, approach):
        from deepsignal.cameras import camera_for
        return camera_for(self.rig, approach)

    def capture(self):
        frame_id = self.world.tick(20)
        frames = {}
        for (name, pending) in self.queues.items():
            while True:
                frame = pending.get(timeout=20)
                if frame.frame == frame_id:
                    frames[name] = carla_image_to_bgr(frame)
                    break
                if frame.frame > frame_id:
                    raise RuntimeError('相机帧号超过当前同步帧')
        composite = compose_tiled_frame(frames, self.rig, draw_labels=False)
        self.last_instances = {}
        self.last_semantics = {}
        for (name, pending) in self.instance_queues.items():
            while True:
                frame = pending.get(timeout=20)
                if frame.frame > frame_id:
                    raise RuntimeError('instance camera frame is ahead of RGB')
                if frame.frame == frame_id:
                    pixels = np.frombuffer(frame.raw_data, dtype=np.uint8).reshape(frame.height, frame.width, 4)
                    self.last_instances[name] = pixels[:, :, 1].astype(np.uint16) + pixels[:, :, 0].astype(np.uint16) * 256
                    self.last_semantics[name] = pixels[:, :, 2].copy()
                    break
        (tile_w, tile_h) = (self.rig.tile_width, self.rig.tile_height)
        for (name, (x, y)) in slot_offsets(self.rig).items():
            label = '+'.join(covers_of(self.rig, name))
            cv2.rectangle(composite, (x + 8, y + 8), (x + 70, y + 47), (20, 20, 20), -1)
            cv2.putText(composite, label, (x + 18, y + 38), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        if getattr(self, 'guides', None):
            composite = draw_lane_guides(composite, self.guides, self.rig)
        return (frame_id, composite)

    def write_signal(self, state):
        if state != getattr(self, '_written_signal', None):
            if getattr(self, 'signal_visuals', None) is not None:
                states = {}
                if self.sumo_connection is not None:
                    states = {tid: self.sumo_connection.trafficlight.getRedYellowGreenState(tid) for tid in self.sumo_connection.trafficlight.getIDList()}
                states[profile.tls_id] = state
                self.signal_visuals.update(states)
            else:
                self.mirror.write(state)
                self.client.apply_batch_sync([], False)
            self._written_signal = state

    def read_signals(self, state, frame_id):
        if self.signal_visuals is not None:
            return self._written_signal == state
        try:
            return self.mirror.read_back(state)
        except RuntimeError:
            write_json(self.output / 'signal-mismatch.json', {'sensor_frame': frame_id, 'snapshot_frame': self.world.get_snapshot().frame, 'expected_state': state, 'channels': {name: {'state': str(light.get_state()), 'frozen': light.is_frozen()} for (name, (light, _)) in self.mirror.channels.items()}})
            raise

    def nansha_transform(self, position, angle, actor):
        box = self.vehicle_boxes[actor.id]
        half = actor_front_offset(actor)
        theta = math.radians(90 - angle)
        yaw = angle - 90.0
        x = position[0] - self.scene_origin[0] - half * math.cos(theta)
        y = -(position[1] - self.scene_origin[1] - half * math.sin(theta))
        heading = math.radians(yaw)
        (bx, by) = (box.location.x, box.location.y)
        x += -bx * math.cos(heading) + by * math.sin(heading)
        y += -bx * math.sin(heading) - by * math.cos(heading)
        z = 0.04 + 0.015 - (box.location.z - box.extent.z)
        rotation = {'yaw': yaw}
        if self.photo_surface is not None:
            (x, y, dz, rotation['yaw'], rotation['pitch']) = self.photo_surface.pose(x, y, yaw)
            z += dz
        return carla.Transform(carla.Location(x=x, y=y, z=z), carla.Rotation(**rotation))

    def sync_vehicles(self, connection, active, appearances, turn_by_vehicle=None, turn_blinkers=False):
        blinks = {'l': carla.VehicleLightState.LeftBlinker, 'r': carla.VehicleLightState.RightBlinker}
        for vehicle_id in set(self.vehicles) - set(active):
            actor = self.vehicles.pop(vehicle_id)
            self.vehicle_boxes.pop(actor.id, None)
            actor.destroy()
        poses = {v: (connection.vehicle.getPosition3D(v), connection.vehicle.getAngle(v)) for v in active}
        nansha = getattr(self, 'scene_origin', None) is not None
        for vehicle_id in active:
            if vehicle_id in self.vehicles:
                actor = self.vehicles[vehicle_id]
                (position, angle) = poses[vehicle_id]
                actor.set_transform(self.nansha_transform(position, angle, actor) if nansha else sumo_to_carla_transform(position, angle, self.offset, half_length=actor_front_offset(actor)))
        if any((v not in self.vehicles for v in active)):
            self.client.apply_batch_sync([], False)
        spawn_failures = []
        for vehicle_id in active:
            if vehicle_id not in self.vehicles:
                (position, angle) = poses[vehicle_id]
                bp = self.world.get_blueprint_library().find('vehicle.ue4.audi.tt')
                bp.set_attribute('role_name', 'deepsignal_r3')
                bp.set_attribute('color', appearances[vehicle_id])
                lifted = None
                if nansha:
                    lifted = carla.Transform(carla.Location(x=position[0] - self.scene_origin[0], y=-(position[1] - self.scene_origin[1]), z=50.0), carla.Rotation(yaw=angle - 90.0))
                actor = self.world.try_spawn_actor(bp, lifted or sumo_to_carla_transform(position, angle, self.offset))
                if actor is None:
                    spawn_failures.append(vehicle_id)
                    continue
                actor.set_simulate_physics(False)
                self.vehicles[vehicle_id] = actor
                self.vehicle_boxes[actor.id] = actor.bounding_box
                actor.set_transform(self.nansha_transform(position, angle, actor) if nansha else sumo_to_carla_transform(position, angle, self.offset, half_length=actor_front_offset(actor)))
                if turn_by_vehicle is not None and turn_blinkers:
                    blinker = blinks.get(turn_by_vehicle.get(vehicle_id))
                    if blinker is not None:
                        actor.set_light_state(blinker)
                self.client.apply_batch_sync([], False)
        if spawn_failures:
            raise RuntimeError(f'CARLA 车辆 spawn 失败: {spawn_failures[:5]}（共{len(spawn_failures)}辆）')

    def __exit__(self, *exc):
        for actor in self.vehicles.values():
            actor.destroy()
        self.vehicles.clear()
        for (light, state, frozen) in self.original_lights:
            light.set_state(state)
            light.freeze(frozen)
        if self.signal_visuals is not None:
            self.signal_visuals.close()
        if hasattr(self, 'weather'):
            self.world.set_weather(self.weather)
        self.session.__exit__(*exc)

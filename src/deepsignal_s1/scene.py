"""Four-camera UE5 rendering and SUMO vehicle/signal mirroring."""

from __future__ import annotations

import math
from pathlib import Path
import queue
import random
import subprocess

import cv2
import numpy as np

from .data import read_json


ORDER = ("E", "W", "S", "N")


def degrade(image, condition):
    if condition == "motion-blur":
        return cv2.filter2D(image, -1, np.ones((1, 9), dtype=np.float32) / 9)
    if condition == "defocus":
        return cv2.GaussianBlur(image, (0, 0), 2.5)
    if condition != "clean":
        raise ValueError(f"Unknown visual condition: {condition}")
    return image


class CameraScene:
    def __init__(self, scene, assets, output, *, host, port, record, condition):
        import carla

        self.carla, self.scene = carla, scene
        self.output, self.record, self.condition = Path(output), record, condition
        self.client = carla.Client(host, port)
        self.client.set_timeout(30)
        if not self.client.get_server_version().startswith("0.10."):
            raise RuntimeError(
                "This scene requires the matching CARLA UE5 0.10 client and server"
            )
        self.world = self.client.get_world()
        if scene["id"] == "town10hd" and "Town10HD" not in self.world.get_map().name:
            raise RuntimeError("The dedicated server must already be running Town10HD")
        self.assets = Path(assets) if assets else None
        self.cameras, self.queues, self.vehicles = {}, {}, {}
        self.visuals = []
        self.native = []
        self.encoder = None
        self.hidden = set()
        self.original_settings = None
        self.trace = None

    def __enter__(self):
        c = self.carla
        if self.world.get_actors().filter(
            "vehicle.*"
        ) or self.world.get_actors().filter("sensor.*"):
            raise RuntimeError(
                "Use an idle dedicated CARLA server; existing actors will not be removed"
            )
        self.original_settings = self.world.get_settings()
        self.original_weather = self.world.get_weather()
        try:
            settings = self.world.get_settings()
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = 0.2 if self.record else 0.1
            if self.record:
                settings.max_substeps = 20
            self.world.apply_settings(settings)
            self.world.set_weather(c.WeatherParameters.ClearNoon)
            library = self.world.get_blueprint_library()
            poses = self.scene["cameras"] or self._town_cameras()
            for label, pose in poses.items():
                bp = library.find("sensor.camera.rgb")
                width, height = (
                    self.scene["tile_size"] if self.record
                    else (pose["image_width"], pose["image_height"])
                )
                bp.set_attribute("image_size_x", str(width))
                bp.set_attribute("image_size_y", str(height))
                bp.set_attribute("fov", str(pose["fov"]))
                x, y, z = pose["location"]
                camera = self.world.spawn_actor(
                    bp,
                    c.Transform(
                        c.Location(x=x, y=y, z=z), c.Rotation(**pose["rotation"])
                    ),
                )
                self.cameras[label] = camera
                self.queues[label] = queue.Queue()
                camera.listen(self.queues[label].put)
            for light in self.world.get_actors().filter("traffic.traffic_light"):
                self.native.append((light, light.get_state(), light.is_frozen()))
                light.freeze(True)
                light.set_state(c.TrafficLightState.Red)
            if self.scene["id"].startswith("nansha"):
                for fixture in read_json(
                    Path(self.scene["network_path"]).parent / "signals.json"
                ):
                    x, y, z = fixture["point"]
                    ux, uy = fixture["u"]
                    transform = c.Transform(
                        c.Location(x=x, y=-y, z=z),
                        c.Rotation(yaw=math.degrees(math.atan2(-uy, ux))),
                    )
                    bps = {
                        s: library.find(
                            f"static.prop.nanshasignal_{fixture['shape']}_{s}"
                        )
                        for s in ("red", "yellow", "green")
                    }
                    self.visuals.append(
                        {
                            "fixture": fixture,
                            "transform": transform,
                            "blueprints": bps,
                            "actor": None,
                            "state": None,
                        }
                    )
                self.hidden = {
                    o.id
                    for o in self.world.get_environment_objects(c.CityObjectLabel.Any)
                    if o.name.startswith("BP_TLOpenDrive_RHT_C_")
                }
                self.world.enable_environment_objects(self.hidden, False)
            for _ in range(15):
                self._capture()
            if self.record:
                width, height = self.scene["tile_size"]
                self.encoder = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-f",
                        "rawvideo",
                        "-pix_fmt",
                        "bgr24",
                        "-s",
                        f"{width * 2}x{height * 2}",
                        "-r",
                        "5",
                        "-i",
                        "pipe:0",
                        "-an",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "19",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        str(self.output / "cameras.mp4"),
                    ],
                    stdin=subprocess.PIPE,
                )
                self.trace = (self.output / "video-trace.jsonl").open(
                    "w", encoding="utf-8"
                )
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _town_cameras(self):
        lights = {
            light.get_opendrive_id(): light
            for light in self.world.get_actors().filter("traffic.traffic_light")
        }
        selected = {
            a: lights[str(identifier)]
            for a, identifier in self.scene["native_lights"][
                "straight_light_odr"
            ].items()
        }
        stops = {a: list(light.get_stop_waypoints()) for a, light in selected.items()}
        positions = {
            a: tuple(
                sum(getattr(w.transform.location, coord) for w in points) / len(points)
                for coord in ("x", "y", "z")
            )
            for a, points in stops.items()
        }
        center = tuple(
            sum(p[i] for p in positions.values()) / len(positions) for i in (0, 1)
        )
        result = {}
        for a, location in positions.items():
            pose = self.scene["camera_mounts"][a]
            dx, dy = center[0] - location[0], center[1] - location[1]
            length = math.hypot(dx, dy)
            dx, dy = dx / length, dy / length
            result[a] = {
                "location": [
                    location[0]
                    + dx * pose["inward_offset"]
                    - dy * pose["lateral_offset"],
                    location[1]
                    + dy * pose["inward_offset"]
                    + dx * pose["lateral_offset"],
                    location[2] + pose["height"],
                ],
                "rotation": {
                    "pitch": pose["pitch"],
                    "yaw": stops[a][0].transform.rotation.yaw + 180,
                },
                "image_width": 1280,
                "image_height": 720,
                "fov": 90,
            }
        return result

    def _capture(self):
        frame_id = self.world.tick(30)
        width, height = self.scene["tile_size"]
        composite = np.zeros((height * 2, width * 2, 3), np.uint8)
        for index, direction in enumerate(ORDER):
            if direction not in self.queues:
                continue
            while True:
                frame = self.queues[direction].get(timeout=30)
                if frame.frame > frame_id:
                    raise RuntimeError("Camera sample is ahead of the simulation frame")
                if frame.frame == frame_id:
                    break
            pixels = np.frombuffer(frame.raw_data, np.uint8).reshape(
                frame.height, frame.width, 4
            )[:, :, :3]
            x, y = index % 2 * width, index // 2 * height
            composite[y : y + height, x : x + width] = cv2.resize(
                pixels, (width, height), interpolation=cv2.INTER_AREA
            )
        return composite

    def _pose(self, position, angle, actor):
        c = self.carla
        origin = self.scene["scene_origin"]
        box = actor.bounding_box
        front = box.location.x + box.extent.x
        theta = math.radians(90 - angle)
        x = position[0] - origin[0] - front * math.cos(theta)
        y = -(position[1] - origin[1] - front * math.sin(theta))
        yaw = angle - 90
        if self.scene["id"].startswith("nansha"):
            heading = math.radians(yaw)
            x += -box.location.x * math.cos(heading) + box.location.y * math.sin(
                heading
            )
            y += -box.location.x * math.sin(heading) - box.location.y * math.cos(
                heading
            )
            z = 0.055 - (box.location.z - box.extent.z)
        else:
            z = position[2] + 0.5
        return c.Transform(c.Location(x=x, y=y, z=z), c.Rotation(yaw=yaw))

    def _signals(self, connection, state):
        c = self.carla
        for head in self.visuals:
            values = {
                "green" if state[i] in "Gg" else "yellow" if state[i] in "yY" else "red"
                for i in head["fixture"]["indices"]
            }
            if len(values) != 1:
                raise RuntimeError("Incompatible states share a visible signal fixture")
            value = values.pop()
            if value != head["state"]:
                new = self.world.spawn_actor(
                    head["blueprints"][value], head["transform"]
                )
                new.set_simulate_physics(False)
                if head["actor"]:
                    head["actor"].destroy()
                head["actor"], head["state"] = new, value
        if not self.visuals:
            native = {light.get_opendrive_id(): light for light, _, _ in self.native}
            from .data import signal_links

            links, _ = signal_links(self.scene)
            for key, mapping in self.scene["native_lights"].items():
                kind = "L" if key.startswith("left") else "SR"
                for approach, identifier in mapping.items():
                    indices = [
                        index
                        for phase in self.scene["phases"]
                        if [approach, kind] in phase["movements"]
                        for index in links[phase["key"]]
                    ]
                    colors = [state[i] for i in indices]
                    color = (
                        c.TrafficLightState.Green
                        if "G" in colors
                        else c.TrafficLightState.Yellow
                        if "y" in colors
                        else c.TrafficLightState.Red
                    )
                    native[str(identifier)].set_state(color)

    def capture(self, connection, plan, state):
        c = self.carla
        active = set(connection.vehicle.getIDList())
        for vehicle in set(self.vehicles) - active:
            self.vehicles.pop(vehicle).destroy()
        palette = ("35,75,150", "150,35,35", "210,210,210", "40,40,40", "200,150,45")
        rng = random.Random(plan["seed"])
        appearances = {v["vehicle_id"]: rng.choice(palette) for v in plan["vehicles"]}
        for vehicle in sorted(active):
            position = connection.vehicle.getPosition3D(vehicle)
            angle = connection.vehicle.getAngle(vehicle)
            actor = self.vehicles.get(vehicle)
            if actor is None:
                bp = self.world.get_blueprint_library().find(
                    self.scene["vehicle_blueprint"]
                )
                bp.set_attribute("role_name", "deepsignal_s1_demo")
                bp.set_attribute("color", appearances[vehicle])
                origin = self.scene["scene_origin"]
                actor = self.world.try_spawn_actor(
                    bp,
                    c.Transform(
                        c.Location(
                            x=position[0] - origin[0],
                            y=-(position[1] - origin[1]),
                            z=50,
                        )
                    ),
                )
                if actor is None:
                    raise RuntimeError(f"Could not render active vehicle {vehicle}")
                actor.set_simulate_physics(False)
                self.vehicles[vehicle] = actor
            actor.set_transform(self._pose(position, angle, actor))
        self._signals(connection, state)
        self.client.apply_batch_sync([], False)
        composite = degrade(self._capture(), self.condition)
        if self.encoder:
            self.encoder.stdin.write(composite.tobytes())
        if (
            not (self.output / "scene.jpg").exists()
            and connection.simulation.getTime() >= plan["window"][0] + 30
        ):
            cv2.imwrite(str(self.output / "scene.jpg"), composite)
        return cv2.imencode(".jpg", composite, [cv2.IMWRITE_JPEG_QUALITY, 92])[
            1
        ].tobytes()

    def encode_model_input(self, jpg):
        image = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        image = cv2.resize(
            image, tuple(self.scene["model_input_size"]), interpolation=cv2.INTER_AREA
        )
        return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()

    def write_trace(self, snapshot):
        import json

        if self.trace:
            self.trace.write(json.dumps(snapshot) + "\n")

    def __exit__(self, *exc):
        encoding_error = False
        if self.trace:
            self.trace.close()
        if self.encoder:
            self.encoder.stdin.close()
            encoding_error = self.encoder.wait() != 0
        for camera in self.cameras.values():
            camera.stop()
            camera.destroy()
        for actor in self.vehicles.values():
            actor.destroy()
        for head in self.visuals:
            if head["actor"]:
                head["actor"].destroy()
        for light, state, frozen in self.native:
            light.set_state(state)
            light.freeze(frozen)
        if self.hidden:
            self.world.enable_environment_objects(self.hidden, True)
        if self.original_settings:
            self.world.apply_settings(self.original_settings)
            self.world.set_weather(self.original_weather)
        if encoding_error and exc[0] is None:
            raise RuntimeError("Video encoding failed")

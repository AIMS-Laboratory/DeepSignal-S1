from __future__ import annotations
import json
import math
from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path
from typing import Any
import carla
from .intersection import approach_location, approach_outward_yaw, junction_center, representative_lights
TILE_ORDER = ('E', 'W', 'S', 'N')
TILE_LABELS = {'E': 'East (东)', 'S': 'South (南)', 'W': 'West (西)', 'N': 'North (北)'}

@dataclass(frozen=True)
class CameraPose:
    height: float = 7.0
    pitch: float = -38.0
    inward_offset: float = 12.0
    lateral_offset: float = 0.0
    x_offset: float = 0.0
    y_offset: float = 0.0
    yaw_offset: float = 0.0

def _default_poses() -> dict[str, CameraPose]:
    return {direction: CameraPose() for direction in TILE_ORDER}

@dataclass(frozen=True)
class PanelSpec:
    slot: tuple[int, int]
    anchor: str
    covers: tuple[str, ...]

@dataclass(frozen=True)
class CameraRigConfig:
    tile_width: int = 640
    tile_height: int = 360
    fov: float = 90.0
    poses: dict[str, CameraPose] = field(default_factory=_default_poses)
    panels: tuple[PanelSpec, ...] = ()

    def __post_init__(self) -> None:
        if self.tile_width <= 0 or self.tile_height <= 0:
            raise ValueError('相机分辨率必须为正数')
        missing = set(TILE_ORDER).difference(self.poses)
        if not self.panels and missing:
            raise ValueError(f'缺少相机方向配置: {sorted(missing)}')
        if self.panels:
            covered: list[str] = []
            for panel in self.panels:
                unknown = set(panel.covers).difference(TILE_ORDER)
                if unknown:
                    raise ValueError(f'panel {panel.anchor} covers 含未知进口: {sorted(unknown)}')
                if panel.anchor not in self.poses:
                    raise ValueError(f'panel {panel.anchor} 缺少对应 pose')
                covered.extend(panel.covers)
            if sorted(covered) != sorted(TILE_ORDER):
                raise ValueError('panels 的 covers 必须无重叠地覆盖全部四进口')
            slots = [panel.slot for panel in self.panels]
            if len(set(slots)) != len(slots):
                raise ValueError('panel slot 不得重叠')

def load_camera_rig_config(path: Path | str) -> CameraRigConfig:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    raw_poses = data.pop('poses')
    raw_panels = data.pop('panels', None)
    if raw_panels is None:
        poses = {direction: CameraPose(**raw_poses[direction]) for direction in TILE_ORDER}
    else:
        poses = {name: CameraPose(**pose) for (name, pose) in raw_poses.items()}
    panels = tuple((PanelSpec(slot=tuple(p['slot']), anchor=p['anchor'], covers=tuple(p['covers'])) for p in raw_panels)) if raw_panels else ()
    return CameraRigConfig(poses=poses, panels=panels, **data)

def slot_offsets(config: CameraRigConfig) -> dict[str, tuple[int, int]]:
    if config.panels:
        return {panel.anchor: (panel.slot[0] * config.tile_width, panel.slot[1] * config.tile_height) for panel in config.panels}
    return {d: (config.tile_width if d in 'WN' else 0, config.tile_height if d in 'SN' else 0) for d in TILE_ORDER}

def camera_for(config: CameraRigConfig, approach: str) -> str:
    if config.panels:
        for panel in config.panels:
            if approach in panel.covers:
                return panel.anchor
        raise ValueError(f'没有 panel 覆盖进口 {approach}')
    return approach

def covers_of(config: CameraRigConfig, camera: str) -> tuple[str, ...]:
    if config.panels:
        for panel in config.panels:
            if panel.anchor == camera:
                return panel.covers
        raise ValueError(f'未知相机 {camera}')
    return (camera,)

def mount_forward_cameras(world: Any, lights: list[Any], config: CameraRigConfig, register_actor: Callable[[Any], Any] | None=None) -> dict[str, Any]:
    center = junction_center(lights)
    representatives = representative_lights(lights)
    blueprint = world.get_blueprint_library().find('sensor.camera.rgb')
    blueprint.set_attribute('image_size_x', str(config.tile_width))
    blueprint.set_attribute('image_size_y', str(config.tile_height))
    blueprint.set_attribute('fov', str(config.fov))
    cameras: dict[str, Any] = {}
    if config.panels:
        for panel in config.panels:
            pose = config.poses[panel.anchor]
            corner_x = corner_y = 0.0
            for approach in panel.covers:
                location = approach_location(representatives[approach])
                (unit_x, unit_y) = (location[0] - center[0], location[1] - center[1])
                norm = math.hypot(unit_x, unit_y) or 1.0
                corner_x += unit_x / norm
                corner_y += unit_y / norm
            corner_norm = math.hypot(corner_x, corner_y)
            if corner_norm < 1e-06:
                raise RuntimeError(f'panel {panel.anchor} 的 covers 进口方向对冲，无法定角点')
            corner_x /= corner_norm
            corner_y /= corner_norm
            ground_z = max((approach_location(representatives[a])[2] for a in panel.covers))
            position_x = center[0] + corner_x * pose.inward_offset + pose.x_offset
            position_y = center[1] + corner_y * pose.inward_offset + pose.y_offset
            inward_yaw = math.degrees(math.atan2(-corner_y, -corner_x))
            camera = world.spawn_actor(blueprint, carla.Transform(carla.Location(x=position_x, y=position_y, z=ground_z + pose.height), carla.Rotation(pitch=pose.pitch, yaw=inward_yaw + pose.yaw_offset)))
            if register_actor is not None:
                register_actor(camera)
            cameras[panel.anchor] = camera
        return cameras
    for direction in TILE_ORDER:
        light = representatives.get(direction)
        if light is None:
            continue
        pose = config.poses[direction]
        location = approach_location(light)
        outward_yaw = approach_outward_yaw(light, center)
        inward_x = center[0] - location[0]
        inward_y = center[1] - location[1]
        inward_length = (inward_x ** 2 + inward_y ** 2) ** 0.5
        if inward_length <= 1e-06:
            raise RuntimeError(f'{direction} 进口相机无法确定路口内侧方向')
        inward_x /= inward_length
        inward_y /= inward_length
        (lateral_x, lateral_y) = (-inward_y, inward_x)
        transform = carla.Transform(carla.Location(x=location[0] + inward_x * pose.inward_offset + lateral_x * pose.lateral_offset + pose.x_offset, y=location[1] + inward_y * pose.inward_offset + lateral_y * pose.lateral_offset + pose.y_offset, z=location[2] + pose.height), carla.Rotation(pitch=pose.pitch, yaw=outward_yaw + pose.yaw_offset))
        camera = world.spawn_actor(blueprint, transform)
        if register_actor is not None:
            register_actor(camera)
        cameras[direction] = camera
    return cameras

from __future__ import annotations
import math
from collections.abc import Sequence
from typing import Any, TypeVar
LightT = TypeVar('LightT')
CARDINALS = ('E', 'N', 'W', 'S')

def yaw_to_cardinal(yaw: float) -> str:
    return CARDINALS[int((yaw % 360 + 45) // 90) % 4]

def junction_center(lights: Sequence[Any]) -> tuple[float, float]:
    if not lights:
        raise ValueError('路口信号灯列表不能为空')
    locations = [approach_location(light) for light in lights]
    return (sum((location[0] for location in locations)) / len(locations), sum((location[1] for location in locations)) / len(locations))

def approach_location(light: Any) -> tuple[float, float, float]:
    if hasattr(light, 'get_stop_waypoints'):
        waypoints = list(light.get_stop_waypoints())
        if waypoints:
            locations = [waypoint.transform.location for waypoint in waypoints]
            return (sum((location.x for location in locations)) / len(locations), sum((location.y for location in locations)) / len(locations), sum((location.z for location in locations)) / len(locations))
    location = light.get_location()
    return (float(location.x), float(location.y), float(getattr(location, 'z', 0.0)))

def approach_outward_yaw(light: Any, center: tuple[float, float]) -> float:
    if hasattr(light, 'get_stop_waypoints'):
        waypoints = list(light.get_stop_waypoints())
        if waypoints:
            return float(waypoints[0].transform.rotation.yaw) + 180.0
    location = approach_location(light)
    return math.degrees(math.atan2(location[1] - center[1], location[0] - center[0]))

def light_direction(light: Any, center: tuple[float, float]) -> str:
    location = approach_location(light)
    yaw = math.degrees(math.atan2(location[1] - center[1], location[0] - center[0]))
    return yaw_to_cardinal(yaw)

def representative_lights(lights: Sequence[LightT]) -> dict[str, LightT]:
    center = junction_center(lights)
    chosen: dict[str, LightT] = {}
    for light in lights:
        direction = light_direction(light, center)
        current = chosen.get(direction)
        if current is None:
            chosen[direction] = light
            continue
        location = approach_location(light)
        current_location = approach_location(current)
        distance = (location[0] - center[0]) ** 2 + (location[1] - center[1]) ** 2
        current_distance = (current_location[0] - center[0]) ** 2 + (current_location[1] - center[1]) ** 2
        if distance < current_distance:
            chosen[direction] = light
    return chosen

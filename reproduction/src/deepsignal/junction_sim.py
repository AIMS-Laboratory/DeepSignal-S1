from __future__ import annotations
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from .junction_profile import active_profile
from .ue4_junction import APPROACH_EDGES, TARGET_JUNCTION_ID
_PROFILE = active_profile()
STRAIGHT_LIGHT_ODR = _PROFILE.straight_light_odr
LEFT_LIGHT_ODR = _PROFILE.left_light_odr

def resolve_channels(world: Any, net_file: Path) -> tuple[dict[str, tuple[Any, tuple[int, ...]]], dict[str, Any]]:
    from .ue4_junction import approach_channels
    channels_by_approach = approach_channels(net_file)
    junction_lights = list(world.get_traffic_lights_in_junction(TARGET_JUNCTION_ID))
    junction_odr = {l.get_opendrive_id(): l for l in junction_lights}
    all_odr = {l.get_opendrive_id(): l for l in world.get_actors().filter('traffic.traffic_light')}
    root = ET.parse(net_file).getroot()
    location = root.find('location')
    assert location is not None
    (ox, oy) = map(float, location.attrib['netOffset'].split(','))
    channels: dict[str, tuple[Any, tuple[int, ...]]] = {}
    mapping_report: dict[str, Any] = {}
    for approach in ('E', 'W', 'S', 'N'):
        straight = junction_odr.get(STRAIGHT_LIGHT_ODR[approach])
        left = all_odr.get(LEFT_LIGHT_ODR[approach])
        if straight is None or left is None:
            raise RuntimeError(f'{approach} 进口缺少可用的原生灯 actor')
        if left.get_opendrive_id() in junction_odr:
            raise RuntimeError(f'{approach} 左转通道必须复用路口外的上游灯')
        lane = root.find(f"edge[@id='{APPROACH_EDGES[approach]}']/lane[@index='3']")
        assert lane is not None
        endpoint = [tuple(map(float, p.split(',')[:2])) for p in lane.attrib['shape'].split()][-1]
        (end_x, end_y) = (endpoint[0] - ox, oy - endpoint[1])

        def stop_distance(light: Any) -> float:
            stops = [w.transform.location for w in light.get_stop_waypoints()]
            if not stops:
                raise RuntimeError(f'灯 {light.get_opendrive_id()} 没有原生停止点')
            return min((abs(s.x - end_x) + abs(s.y - end_y) for s in stops))
        if stop_distance(straight) > 12.0:
            raise RuntimeError(f'{approach} 直右灯的停止点不靠近本进口车道端点')
        if stop_distance(left) <= 12.0:
            raise RuntimeError(f'{approach} 左转复用灯的停止点落在受控进口上，会干扰本次交通')
        channels[f'{approach}_straight'] = (straight, channels_by_approach[approach]['straight'])
        channels[f'{approach}_left'] = (left, channels_by_approach[approach]['left'])
        for (kind, light) in (('straight', straight), ('left', left)):
            mapping_report[f'{approach}_{kind}'] = {'actor_id': light.id, 'opendrive_id': light.get_opendrive_id(), 'origin': 'junction 189 原生灯，停止点绑定本进口行驶车道' if kind == 'straight' else '上游原生灯复用为左转信号通道，原始停止线不在本次交通边上', 'sumo_link_indices': channels_by_approach[approach][kind], 'original_stop_waypoints': [{'road': w.road_id, 'lane': w.lane_id} for w in light.get_stop_waypoints()]}
    return (channels, mapping_report)

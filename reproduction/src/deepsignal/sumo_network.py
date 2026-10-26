from __future__ import annotations
from pathlib import Path
from lxml import etree
from .spatial import DEFAULT_SPATIAL_CONFIG_PATH, load_stop_line_geometry, load_sumo_stop_offsets

def apply_target_stop_offsets(net_file: Path, offsets_by_edge: dict[str, float] | None=None) -> None:
    offsets = offsets_by_edge or load_sumo_stop_offsets()
    tree = etree.parse(str(net_file), etree.XMLParser(remove_blank_text=False))
    edges = {str(edge.get('id')): edge for edge in tree.getroot().findall('edge')}
    for (edge_id, value) in offsets.items():
        edge = edges.get(edge_id)
        if edge is None:
            raise RuntimeError(f'SUMO 路网缺少待校准目标进口 {edge_id}')
        lane_lengths = [float(lane.get('length', '0')) for lane in edge.findall('lane')]
        if not lane_lengths or value >= min(lane_lengths):
            raise ValueError(f'目标进口 {edge_id} 的停车偏移超出车道长度')
        existing = edge.find('stopOffset')
        if existing is None:
            existing = etree.SubElement(edge, 'stopOffset')
        existing.set('value', f'{value:.3f}')
    tree.write(str(net_file), encoding='UTF-8', xml_declaration=True, pretty_print=False)

def _parse_shape(value: str) -> list[tuple[float, float]]:
    return [(float(pair.split(',')[0]), float(pair.split(',')[1])) for pair in value.split()]

def _format_shape(points: list[tuple[float, float]]) -> str:
    return ' '.join((f'{x:.3f},{y:.3f}' for (x, y) in points))

def _trim_internal_shape(points: list[tuple[float, float]], distance: float, new_start: tuple[float, float]) -> list[tuple[float, float]]:
    remaining = distance
    for (index, (start, end)) in enumerate(zip(points, points[1:])):
        segment = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        if segment <= 1e-09:
            continue
        if remaining <= segment:
            fraction = remaining / segment
            clipped = (start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction)
            tail = [clipped, *points[index + 1:]]
            if ((tail[0][0] - new_start[0]) ** 2 + (tail[0][1] - new_start[1]) ** 2) ** 0.5 < 0.001:
                tail[0] = new_start
                return tail
            return [new_start, *tail]
        remaining -= segment
    raise ValueError('实体停车线超过目标内部连接的可裁剪长度')

def align_target_lane_boundaries(net_file: Path, *, spatial_config_path: Path=DEFAULT_SPATIAL_CONFIG_PATH) -> None:
    tree = etree.parse(str(net_file), etree.XMLParser(remove_blank_text=False))
    root = tree.getroot()
    location = root.find('location')
    if location is None or not location.get('netOffset'):
        raise RuntimeError('SUMO 路网缺少坐标偏移')
    (offset_x, offset_y) = (float(value) for value in str(location.get('netOffset')).split(','))
    lines = load_stop_line_geometry(spatial_config_path)
    edge_by_approach = {'E': '20', 'W': '-18', 'S': '-22', 'N': '-14'}
    edges = {str(edge.get('id')): edge for edge in root.findall('edge')}
    lanes = {str(lane.get('id')): lane for edge in root.findall('edge') for lane in edge.findall('lane')}
    changed = False
    for (approach, edge_id) in edge_by_approach.items():
        edge = edges.get(edge_id)
        if edge is None:
            raise RuntimeError(f'SUMO 路网缺少待校准目标进口 {edge_id}')
        line = lines[approach]
        sumo_travel = (line.travel_direction[0], -line.travel_direction[1])
        moved_lanes: dict[str, tuple[float, tuple[float, float]]] = {}
        for lane in edge.findall('lane'):
            if lane.get('type') != 'driving':
                continue
            shape = _parse_shape(str(lane.get('shape')))
            endpoint = shape[-1]
            carla_endpoint = (endpoint[0] - offset_x, offset_y - endpoint[1])
            distance = (line.center[0] - carla_endpoint[0]) * line.travel_direction[0] + (line.center[1] - carla_endpoint[1]) * line.travel_direction[1]
            if abs(distance) <= 0.001:
                continue
            if not 0.0 < distance < 10.0:
                raise ValueError(f'目标进口 {edge_id} 车道端点距实体停车线 {distance:.3f} 米，不允许自动校准')
            new_endpoint = (endpoint[0] + sumo_travel[0] * distance, endpoint[1] + sumo_travel[1] * distance)
            shape[-1] = new_endpoint
            lane.set('shape', _format_shape(shape))
            old_length = float(lane.get('length', '0'))
            lane.set('length', f'{old_length + distance:.3f}')
            moved_lanes[str(lane.get('index'))] = (distance, new_endpoint)
            changed = True
        for connection in root.findall('connection'):
            if connection.get('from') != edge_id:
                continue
            moved = moved_lanes.get(str(connection.get('fromLane')))
            via_id = connection.get('via')
            if moved is None or not via_id:
                continue
            (distance, new_start) = moved
            via_lane = lanes.get(str(via_id))
            if via_lane is None:
                raise RuntimeError(f'目标进口连接缺少内部车道 {via_id}')
            old_length = float(via_lane.get('length', '0'))
            if distance >= old_length - 0.1:
                raise ValueError(f'内部车道 {via_id} 不足以移动实体停车线边界')
            shape = _parse_shape(str(via_lane.get('shape')))
            via_lane.set('shape', _format_shape(_trim_internal_shape(shape, distance, new_start)))
            via_lane.set('length', f'{old_length - distance:.3f}')
    if changed:
        tree.write(str(net_file), encoding='UTF-8', xml_declaration=True, pretty_print=False)

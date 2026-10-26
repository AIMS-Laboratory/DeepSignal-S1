from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from .junction_profile import active_profile
STOP_LINE_GEOMETRY_VERSION = 'town10hd-189-visible-stop-lines.v1'
DEFAULT_SPATIAL_CONFIG_PATH = Path(__file__).resolve().parents[2] / 'configs/stop_lines.town10hd.json'

@dataclass(frozen=True)
class StopLineGeometry:
    approach: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    center: tuple[float, float, float]
    travel_direction: tuple[float, float, float]
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

def front_bumper_location(actor: Any) -> tuple[float, float, float]:
    transform = actor.get_transform()
    forward = transform.get_forward_vector()
    vertices = list(actor.bounding_box.get_world_vertices(transform))
    if not vertices:
        raise ValueError('CARLA 车辆包围盒没有世界坐标顶点')
    projections = [float(vertex.x) * float(forward.x) + float(vertex.y) * float(forward.y) + float(vertex.z) * float(forward.z) for vertex in vertices]
    maximum = max(projections)
    front_vertices = [vertex for (vertex, projection) in zip(vertices, projections) if abs(projection - maximum) <= 0.0001]
    return (sum((float(vertex.x) for vertex in front_vertices)) / len(front_vertices), sum((float(vertex.y) for vertex in front_vertices)) / len(front_vertices), sum((float(vertex.z) for vertex in front_vertices)) / len(front_vertices))

def actor_front_offset(actor: Any) -> float:
    transform = actor.get_transform()
    center = transform.location
    front = front_bumper_location(actor)
    forward = transform.get_forward_vector()
    return (front[0] - float(center.x)) * float(forward.x) + (front[1] - float(center.y)) * float(forward.y) + (front[2] - float(center.z)) * float(forward.z)

def load_stop_line_geometry(path: Path) -> dict[str, StopLineGeometry]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != STOP_LINE_GEOMETRY_VERSION:
        raise ValueError('停车线几何版本不受支持')
    if str(payload.get('target_junction_id')) != str(active_profile().junction_id):
        raise ValueError('停车线几何不属于目标路口')

    def triple(values: list[Any]) -> tuple[float, float, float]:
        if len(values) != 3:
            raise ValueError('停车线世界坐标必须包含三个数值')
        return (float(values[0]), float(values[1]), float(values[2]))
    stop_lines = {direction: StopLineGeometry(approach=str(data['approach']), start=triple(data['start']), end=triple(data['end']), center=triple(data['center']), travel_direction=triple(data['travel_direction']), source=str(data['source'])) for (direction, data) in payload.get('stop_lines', {}).items()}
    if set(stop_lines) != {'E', 'W', 'S', 'N'}:
        raise ValueError('停车线几何必须完整覆盖东、西、南、北四进口')
    return stop_lines

def load_sumo_stop_offsets(path: Path=DEFAULT_SPATIAL_CONFIG_PATH) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    offsets = {str(edge_id): float(value) for (edge_id, value) in payload.get('calibration', {}).get('sumo_stop_offsets_by_edge', {}).items()}
    if set(offsets) != {'20', '-18', '-14', '-22'}:
        raise ValueError('SUMO 停车位置校准必须覆盖目标路口四个进口')
    if any((value <= 0 for value in offsets.values())):
        raise ValueError('SUMO 停车位置校准值必须为正数')
    return offsets

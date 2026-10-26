import math
import xml.etree.ElementTree as ET
import cv2
import numpy as np
from sumolib.geomhelper import positionAtShapeOffset
from .demand_plan import APPROACH_EDGES
from .cameras import TILE_ORDER, camera_for, covers_of, slot_offsets
from .visibility import project_world_point

def ue5_camera_matrix(transform):
    (yaw, pitch) = (math.radians(transform.rotation.yaw), math.radians(transform.rotation.pitch))
    forward = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    right = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    basis = np.array([forward, right, np.cross(forward, right)])
    position = np.array([transform.location.x, transform.location.y, transform.location.z])
    matrix = np.eye(4)
    matrix[:3, :3] = basis
    matrix[:3, 3] = -basis @ position
    return matrix

def build_lane_guides(net, cameras, rig, scene_origin=None, photo_surface=None):
    root = ET.parse(net).getroot()
    nansha = scene_origin is not None
    if not nansha:
        (ox, oy) = map(float, root.find('location').attrib['netOffset'].split(','))
    from .junction_profile import active_profile, STUB_APPROACH_EDGE_M, observation_edge_chain
    profile = active_profile()

    def project(sumo_x, sumo_y, matrix, fov):
        if nansha:
            (wx, wy) = (sumo_x - scene_origin[0], -(sumo_y - scene_origin[1]))
            wz = 0.0
            if photo_surface is not None:
                (wx, wy, wz) = photo_surface.forward(wx, wy)
            world = (wx, wy, wz + 0.06)
        else:
            world = (sumo_x - ox, oy - sumo_y, 0.06)
        point = project_world_point(world, matrix, rig.tile_width, rig.tile_height, fov)
        if point is None:
            return None
        if nansha and (not (0 <= point[0] < rig.tile_width and 0 <= point[1] < rig.tile_height)):
            return None
        return point
    result = {}
    for (camera_name, camera) in cameras.items():
        matrix = ue5_camera_matrix(camera.get_transform())
        fov = float(camera.attributes.get('fov', rig.fov)) if nansha else rig.fov
        for approach in covers_of(rig, camera_name):
            result[approach] = {}
            if nansha:
                spec = profile.lanes_for(approach)
                groups = {'SR': (*spec.straight_lanes, *spec.shared_sl_lanes), 'L': spec.left_lanes}
            else:
                groups = {'SR': ('3',), 'L': ('4',)}
            for (lane_name, indices) in groups.items():
                (hull_points, label) = ([], None)
                for index in indices:
                    approach_lane = root.find(f"edge[@id='{APPROACH_EDGES[approach]}']/lane[@index='{index}']")
                    if approach_lane is None:
                        continue
                    chain = (APPROACH_EDGES[approach],)
                    if float(approach_lane.attrib['length']) < STUB_APPROACH_EDGE_M:
                        chain = observation_edge_chain(active_profile(), approach)
                    base = 0.0
                    for edge_id in chain:
                        lane = root.find(f"edge[@id='{edge_id}']/lane[@index='{index}']")
                        if lane is None:
                            break
                        shape = [tuple(map(float, s0.split(',')[:2])) for s0 in lane.attrib['shape'].split()]
                        length = sum((math.dist(a, b) for (a, b) in zip(shape, shape[1:])))
                        width = float(lane.attrib.get('width', '3.2'))
                        if length > 0.7:
                            for distance in np.linspace(0.5, min(length - 0.2, 40.0 - base), 16):
                                offset = length - distance
                                point = positionAtShapeOffset(shape, offset)
                                prev = positionAtShapeOffset(shape, max(0, offset - 0.1))
                                following = positionAtShapeOffset(shape, min(length, offset + 0.1))
                                (dx, dy) = (following[0] - prev[0], following[1] - prev[1])
                                scale = math.hypot(dx, dy)
                                for sign in (-1, 1):
                                    x = point[0] - sign * dy / scale * width / 2
                                    y = point[1] + sign * dx / scale * width / 2
                                    projection = project(x, y, matrix, fov)
                                    if projection is not None:
                                        hull_points.append(list(projection[:2]))
                        if label is None:
                            near = positionAtShapeOffset(shape, max(0.0, length - 0.5))
                            mark = project(near[0], near[1], matrix, fov) if near else None
                            if mark is not None:
                                label = list(mark[:2])
                        base += length
                        if base >= 40.0:
                            break
                if not hull_points:
                    result[approach][lane_name] = {'polygon': [], 'label': [16, 20]}
                    continue
                polygon = cv2.convexHull(np.array(hull_points, dtype=np.float32)).reshape(-1, 2).tolist()
                result[approach][lane_name] = {'polygon': polygon, 'label': label or [16, 20]}
    return result

def draw_lane_guides(frame, guides, rig):
    result = frame.copy()
    for (approach, (x, y)) in approach_slots(rig):
        if approach not in guides:
            continue
        tile = result[y:y + rig.tile_height, x:x + rig.tile_width]
        for (label, item) in guides[approach].items():
            color = (240, 180, 20) if label == 'SR' else (40, 220, 250)
            polygon = np.array(item['polygon'], dtype=np.int32)
            cv2.polylines(tile, [polygon], True, color, 1, cv2.LINE_AA)
            (lx, ly) = item['label']
            (lx, ly) = (max(16, min(rig.tile_width - 30, lx)), max(20, min(rig.tile_height - 22, ly + 18)))
            cv2.rectangle(tile, (lx - 17, ly - 15), (lx + 19, ly + 4), (20, 20, 20), -1)
            cv2.putText(tile, label, (lx - 13, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return result

def approach_slots(rig):
    offsets = slot_offsets(rig)
    for approach in TILE_ORDER:
        camera = camera_for(rig, approach)
        yield (approach, offsets[camera])

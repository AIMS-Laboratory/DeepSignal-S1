from __future__ import annotations
import math
import carla

def sumo_to_carla_transform(position: tuple[float, float, float], angle: float, net_offset: tuple[float, float], *, half_length: float=0.0, z_offset: float=0.5) -> carla.Transform:
    yaw_for_center = -angle + 90.0
    center_x = position[0] - math.cos(math.radians(yaw_for_center)) * half_length
    center_y = position[1] - math.sin(math.radians(yaw_for_center)) * half_length
    return carla.Transform(carla.Location(x=center_x - net_offset[0], y=-(center_y - net_offset[1]), z=position[2] + z_offset), carla.Rotation(yaw=angle - 90.0))

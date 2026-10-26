from __future__ import annotations
import numpy as np

def project_world_point(world_point: tuple[float, float, float], camera_world_matrix: np.ndarray, image_width: int, image_height: int, fov_degrees: float) -> tuple[int, int, float] | None:
    point = np.array([*world_point, 1.0])
    camera_point = camera_world_matrix @ point
    (forward, right, up) = camera_point[:3]
    if forward <= 1e-06:
        return None
    focal = image_width / (2.0 * np.tan(np.radians(fov_degrees) / 2.0))
    u = int(round(focal * right / forward + image_width / 2.0))
    v = int(round(image_height / 2.0 - focal * up / forward))
    return (u, v, float(forward))

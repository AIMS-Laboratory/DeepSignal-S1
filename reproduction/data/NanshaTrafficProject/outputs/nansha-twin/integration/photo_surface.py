"""One shared visual bridge surface for geometry, vehicles and RGB ray casting.

The 3.1 m crown and 1.6 m central separation are photographic estimates.
SUMO's lane graph, trajectories and statistics retain their canonical coordinates.
Rendering uses the reversible map below; video measurements invert it.
Coordinates in this module are CARLA metres: east / south / up.
"""
import math, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
_origin = json.loads((ROOT / 'nine/data/coordinate_frame.json').read_text())['scene_origin_sumo_xy_m']
_centers = {j['id']: (j['sumo_xy'][0] - _origin[0], -(j['sumo_xy'][1] - _origin[1])) for j in json.loads((ROOT / 'nine/data/junctions.json').read_text(encoding='utf-8'))}
A = _centers['J07']
B = _centers['J08']
L = math.dist(A, B)
U = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
N = (-U[1], U[0])

def active():
    try:
        return json.loads((ROOT / 'nine/refined/ACTIVE.json').read_text()).get('visual_version') == 'visual-20260922-v6'
    except (OSError, ValueError):
        return False

def coordinates(x, y):
    return ((x - A[0]) * U[0] + (y - A[1]) * U[1], (x - A[0]) * N[0] + (y - A[1]) * N[1])

def envelope(s):
    q = max(0, min(1, (s - 24) / 32, (L - 24 - s) / 32))
    return q * q * (3 - 2 * q)

def centre(s):
    return 0.92 - 0.0026 * s

def height(x, y):
    (s, t) = coordinates(x, y)
    if abs(t) > 14 or not 24 < s < L - 24:
        return 0.0
    return 3.1 * math.sin(math.pi * (s - 24) / (L - 48)) ** 2

def forward(x, y):
    (s, t) = coordinates(x, y)
    if abs(t) > 14:
        return (x, y, 0.0)
    shift = 0.8 * envelope(s) * (1 if t >= centre(s) else -1)
    return (x + N[0] * shift, y + N[1] * shift, height(x, y))

def inverse(x, y):
    (s, t) = coordinates(x, y)
    if abs(t) > 14.8:
        return (x, y)
    shift = 0.8 * envelope(s)
    if shift > 0.01 and abs(t - centre(s)) < shift:
        return None
    sign = 1 if t >= centre(s) else -1
    return (x - N[0] * shift * sign, y - N[1] * shift * sign)

def pose(x, y, yaw):
    a = math.radians(yaw)
    (dx, dy) = (math.cos(a) * 0.7, math.sin(a) * 0.7)
    (x1, y1, z1) = forward(x - dx, y - dy)
    (x2, y2, z2) = forward(x + dx, y + dy)
    (xx, yy, zz) = forward(x, y)
    return (xx, yy, zz, math.degrees(math.atan2(y2 - y1, x2 - x1)), math.degrees(math.atan2(z2 - z1, math.hypot(x2 - x1, y2 - y1))))

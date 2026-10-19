"""Hex-cell conversion for the pygame GUI (pointy-top hexagons)"""

import math
from typing import Optional, Tuple

from ..board.coordinates import Cell, is_valid

def hex_to_pixel(cell: Cell, size: float, origin: Tuple[float, float]) -> Tuple[float, float]:
    col, row = cell

    q, r = col - 4, 5 - row
    x = origin[0] + size * math.sqrt(3) * (q + r / 2)
    y = origin[1] + size * 1.5 * r
    return x, y

def pixel_to_hex(point: Tuple[float, float], size: float, origin: Tuple[float, float]) -> Optional[Cell]:
    px, py = point[0] - origin[0], point[1] - origin[1]
    q = (math.sqrt(3) / 3.0 * px - 1.0 / 3.0 * py) / size
    r = (2.0 / 3.0 * py) / size
    aq, ar = _round_axial(q, r)
    cell = (aq + 4, 5 - ar)
    return cell if is_valid(cell) else None

def _round_axial(q: float, r: float) -> Tuple[int, int]:
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    q_diff, r_diff, s_diff = abs(rq - q), abs(rr - r), abs(rs - s)
    if q_diff > r_diff and q_diff > s_diff:
        rq = -rr - rs
    elif r_diff > s_diff:
        rr = -rq - rs
    return int(rq), int(rr)

def hex_corners(center: Tuple[float, float], size: float):
    corners = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        corners.append((center[0] + size * math.cos(angle), center[1] + size * math.sin(angle)))
    return corners
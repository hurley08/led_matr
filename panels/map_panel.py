"""
panels/map_panel.py — radar map visualization.

Subscribes to: lidar.scan
Panel:         LEFT
"""

from __future__ import annotations

import math
from typing import List

from core import Panel, PanelView, Visualization
from streams import Point

W   = H   = 64
CX  = CY  = 32
PPM = 14          # LED pixels per metre
MAX_DIST = 3000   # mm — colour ceiling


# ── Colour helpers ───────────────────────────────────────────────────────────────

def _hsv_rgb(h: float) -> tuple:
    h6 = (h % 1.0) * 6.0
    i  = int(h6); f = h6 - i
    q  = 1 - f; tv = f
    r, g, b = [(1,tv,0),(q,1,0),(0,1,tv),(0,q,1),(tv,0,1),(1,0,q)][i % 6]
    return int(r * 255), int(g * 255), int(b * 255)

def _dist_color(mm: float) -> tuple:
    """Red (close) → violet (far) across the visible spectrum."""
    t = min(1.0, max(0.0, mm / MAX_DIST))
    return _hsv_rgb(t * 0.75)


# ── Visualization ────────────────────────────────────────────────────────────────

class RadarMap(Visualization):
    """
    Top-down LIDAR radar map.

    Renders a colour-coded point cloud (red = close, violet = far) on a black
    field with a green dotted crosshair, dashed distance rings at 1 m and 2 m,
    a robot marker at centre, a heading arrow, and a distance-colour legend
    strip along the bottom three rows.

    Subscribes to: lidar.scan
    """

    panel   = Panel.LEFT
    streams = ["lidar.scan"]

    def __init__(self, heading_deg: float = 0.0):
        self.heading = heading_deg   # robot heading in degrees (0 = forward)

    def render(self, view: PanelView, *, lidar_scan: List[Point], **_):
        # Distance rings (dashed)
        for dist_m, bright in [(1.0, 65), (2.0, 45)]:
            r_px = dist_m * PPM
            n    = max(1, int(2 * math.pi * r_px / 1.8))
            for i in range(n):
                if i % 3 == 0:
                    continue
                a = 2 * math.pi * i / n
                view.set_pixel(int(CX + r_px * math.sin(a)),
                               int(CY - r_px * math.cos(a)),
                               bright, bright, bright)

        # Green dotted crosshair
        for x in range(W):
            if x % 3 != 0:
                view.set_pixel(x, CY, 0, 65, 0)
        for y in range(H):
            if y % 3 != 0:
                view.set_pixel(CX, y, 0, 65, 0)

        # Point cloud
        for pt in lidar_scan:
            if pt.distance <= 0 or pt.quality == 0:
                continue
            a  = math.radians(pt.angle)
            px = int(CX + (pt.distance / 1000) * PPM * math.sin(a))
            py = int(CY - (pt.distance / 1000) * PPM * math.cos(a))
            view.set_pixel(px, py, *_dist_color(pt.distance))

        # Heading arrow
        a = math.radians(self.heading)
        for i in range(3, 13):
            view.set_pixel(int(CX + i * math.sin(a)),
                           int(CY - i * math.cos(a)),
                           255, 255, 255)

        # Robot marker (hollow square)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if abs(dx) == 2 or abs(dy) == 2:
                    view.set_pixel(CX + dx, CY + dy, 230, 230, 230)

        # Distance legend strip (bottom 3 rows, half-brightness)
        for x in range(W):
            r, g, b = _dist_color(x / (W - 1) * MAX_DIST)
            for row in range(H - 3, H):
                view.set_pixel(x, row, r // 2, g // 2, b // 2)

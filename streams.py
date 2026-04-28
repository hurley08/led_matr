"""
streams.py — data stream definitions for led_matr.

Streams are the single source of truth for sensor data.  Add new streams
here; visualizations can subscribe to any of them by name.

Available streams
─────────────────
  lidar.scan      Raw point cloud — List[Point]
  lidar.sectors   Sector analysis — SectorStats dataclass with front/left/right/min_dist/avg_dist/density/health

Run  `python3 streams.py`  to print a live summary (mock data, no hardware needed).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List

from core import Stream


# ── Data types ───────────────────────────────────────────────────────────────────

@dataclass
class Point:
    angle:    float   # degrees, 0 = forward, clockwise
    distance: float   # mm
    quality:  int     # 0–255


@dataclass
class SectorStats:
    front:    float   # mm — minimum distance in front sector (315°–45°)
    left:     float   # mm — minimum distance in left sector  (225°–315°)
    right:    float   # mm — minimum distance in right sector ( 45°–135°)
    min_dist: float   # mm — global minimum across all points
    avg_dist: float   # mm — global average
    density:  float   # 0–100 — % of angular bins with a valid return
    health:   float   # 0–100 — scan quality estimate


# ── Source implementations ────────────────────────────────────────────────────────

class _RPLidarSource:
    """Real RPLidar sensor (A1/A2/A3/S-series)."""

    def __init__(self, port: str = "/dev/ttyUSB0"):
        from rplidar import RPLidar
        self._lidar = RPLidar(port)
        self._lidar.start_motor()
        self._iter  = self._lidar.iter_scans()

    def get_scan(self) -> List[Point]:
        raw = next(self._iter)
        return [Point(angle=m[1], distance=m[2], quality=m[0]) for m in raw]

    def stop(self):
        self._lidar.stop()
        self._lidar.stop_motor()
        self._lidar.disconnect()


class _MockLidarSource:
    """Deterministic mock — no hardware needed."""

    def __init__(self, seed: int = 99):
        self._rng = random.Random(seed)
        self._t   = 0.0

    def get_scan(self) -> List[Point]:
        self._t += 0.15
        pts = []
        for deg in range(0, 360, 2):
            a    = math.radians(deg)
            wall = 1700 + 450 * math.cos(2 * a) + 280 * math.sin(3 * a + 1.0)
            if 345 <= deg or deg <= 15:
                d = min(wall, 280 + 440 * (0.5 + 0.5 * math.sin(self._t)))
            elif 270 <= deg < 330:
                d = min(wall, 680 + 120 * math.sin(self._t * 0.7))
            else:
                d = wall
            d = max(80, min(4500, d + self._rng.gauss(0, 20)))
            pts.append(Point(deg, d, 200))
        return pts

    def stop(self):
        """No resources to release."""


# ── Sector analysis ───────────────────────────────────────────────────────────────

def _analyze(points: List[Point]) -> SectorStats:
    def sector_min(lo: float, hi: float) -> float:
        if lo < hi:
            ds = [p.distance for p in points if lo <= p.angle < hi and p.quality > 0]
        else:
            ds = [p.distance for p in points
                  if (p.angle >= lo or p.angle < hi) and p.quality > 0]
        return min(ds) if ds else 9999.0

    valid = [p.distance for p in points if p.quality > 0]
    if not valid:
        return SectorStats(9999, 9999, 9999, 9999, 9999, 0, 0)

    return SectorStats(
        front    = sector_min(315, 45),
        left     = sector_min(225, 315),
        right    = sector_min(45,  135),
        min_dist = min(valid),
        avg_dist = sum(valid) / len(valid),
        density  = min(100.0, len(valid) / 1.8),   # 180 bins @ 2° spacing → 100%
        health   = min(100.0, sum(p.quality for p in points) / (len(points) * 2.55)),
    )


# ── Stream factory ────────────────────────────────────────────────────────────────

def build_streams(*, mock: bool = False, port: str = "/dev/ttyUSB0"):
    """
    Return (lidar_scan_stream, sector_stats_stream).

    Pass mock=True on any machine without a connected RPLidar.
    """
    source = _MockLidarSource() if mock else _RPLidarSource(port)

    lidar_scan = Stream(
        name        = "lidar.scan",
        description = "Raw point cloud — List[Point(angle, distance, quality)]",
        source      = source.get_scan,
        on_close    = source.stop,
    )

    lidar_sectors = Stream(
        name        = "lidar.sectors",
        description = "Sector analysis — SectorStats(front/left/right/min/avg/density/health)",
        source      = lambda: _analyze(lidar_scan.latest or []),
        depends_on  = ["lidar.scan"],
    )

    return lidar_scan, lidar_sectors


# ── Quick CLI summary ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    scan_s, sector_s = build_streams(mock=True)

    print("Streaming mock data — Ctrl-C to stop\n")
    print(f"{'Stream':<20} {'Latest value summary'}")
    print("─" * 60)

    try:
        while True:
            scan_s.update()
            sector_s.update()

            pts  = scan_s.latest
            stat = sector_s.latest

            print(f"\r{'lidar.scan':<20} {len(pts)} points   "
                  f"{'lidar.sectors':<14} "
                  f"F={stat.front/1000:.2f}m  "
                  f"L={stat.left/1000:.2f}m  "
                  f"R={stat.right/1000:.2f}m  "
                  f"min={stat.min_dist/1000:.2f}m",
                  end="", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nDone.")

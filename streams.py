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
    front:    float   # mm — minimum distance in front sector (135°–225°)
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
        print(f"[lidar] importing RPLidarA1 ...")
        from rplidar import RPLidarA1
        self._RPLidarA1 = RPLidarA1
        self._port = port
        self._lidar = None
        self._iter  = None
        self._reconnect_count = 0
        print(f"[lidar] connecting to {port!r} ...")
        self._connect()
        print(f"[lidar] connected and motor started")

    def _connect(self):
        if self._lidar is not None:
            try:
                self._lidar.disconnect()
            except Exception:
                pass
        self._lidar = self._RPLidarA1(self._port)
        self._lidar.connect()
        self._lidar.start_motor()
        # Verify the sensor responds before starting scan
        print(f"[lidar] probing sensor health ...")
        import time as _time
        _time.sleep(1.0)   # settle after drain
        for attempt in range(10):
            try:
                self._lidar._drain()
                health = self._lidar.get_health()
                print(f"[lidar] health: {health.status} (err={health.error_code})")
                break
            except Exception as exc:
                print(f"[lidar] health probe {attempt+1}/10 failed: {exc}")
                _time.sleep(0.5)
        else:
            raise Exception("sensor did not respond after 10 health probes")
        self._iter = self._lidar.iter_scans()
        # Block until we get the first valid scan, confirming data is flowing
        print(f"[lidar] waiting for first scan ...")
        import itertools
        first = next(self._iter)
        print(f"[lidar] first scan received: {len(first)} points")
        self._iter = itertools.chain([first], self._iter)

    def get_scan(self) -> List[Point]:
        import serial
        try:
            raw = next(self._iter)
            if self._reconnect_count:
                print(f"[lidar] recovered after {self._reconnect_count} reconnect(s)")
                self._reconnect_count = 0
            return [Point(angle=m[1], distance=m[2], quality=m[0]) for m in raw]
        except (serial.SerialException, StopIteration, Exception) as exc:
            # Device hiccup — reconnect and return empty scan for this frame
            self._reconnect_count += 1
            if self._reconnect_count == 1 or self._reconnect_count % 30 == 0:
                print(f"[lidar] reconnect attempt #{self._reconnect_count} on {self._port!r}: {exc}")
            try:
                self._connect()
            except Exception as exc:
                print(f"[lidar] reconnect failed: {exc}")
            return []

    def stop(self):
        print("[lidar] stopping motor and disconnecting ...")
        try:
            self._lidar.stop()
            self._lidar.stop_motor()
            self._lidar.disconnect()
            print("[lidar] disconnected")
        except Exception as exc:
            print(f"[lidar] stop error (ignored): {exc}")


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

    valid = [p.distance for p in points if p.quality >= 10 and 0 < p.distance < 12000]
    if not valid:
        return SectorStats(9999, 9999, 9999, 9999, 9999, 0, 0)

    return SectorStats(
        front    = sector_min(135, 225),
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
    print(f"[streams] build_streams mock={mock}, port={port!r}")
    source = _MockLidarSource() if mock else _RPLidarSource(port)
    print(f"[streams] source ready: {type(source).__name__}")

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

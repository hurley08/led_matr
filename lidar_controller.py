#!/usr/bin/env python3
"""USB LiDAR controller utilities for Raspberry Pi.

This module provides a small, hardware-friendly wrapper around a USB serial
LiDAR stream. It is intentionally protocol-light and expects one measurement
per line from the sensor firmware, for example:

- "12.5,840"                       -> angle,degrees and distance,mm
- "12.5,840,180"                   -> angle,distance,quality
- "angle:12.5 distance:840 q:180"  -> key:value format
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, Thread
from typing import Callable, List, Optional
import glob
import grp
import os
import pwd
import re
import time

try:
    import serial  # type: ignore
    from serial import SerialException  # type: ignore
except ImportError:  # pragma: no cover - runtime dependency
    serial = None

    class SerialException(Exception):
        """Fallback exception used when pyserial is missing."""


@dataclass(frozen=True)
class LidarMeasurement:
    """Single LiDAR sample."""

    timestamp: float
    angle_deg: float
    distance_mm: float
    quality: Optional[int] = None


class UsbLidarController:
    """Control and read a USB serial LiDAR stream in a background thread.

    This class opens a serial device, parses incoming lines into
    `LidarMeasurement`, and keeps a rolling in-memory buffer.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 230400,
        timeout: float = 0.2,
        max_buffer_size: int = 2048,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.max_buffer_size = max(64, max_buffer_size)

        self._serial = None
        self._thread: Optional[Thread] = None
        self._running = False
        self._lock = Lock()
        self._buffer: List[LidarMeasurement] = []
        self._on_measurement: Optional[Callable[[LidarMeasurement], None]] = None

    @staticmethod
    def detect_port() -> Optional[str]:
        """Return the first likely USB serial device path, if any."""
        candidates = sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))
        return candidates[0] if candidates else None

    def connect(self) -> str:
        """Open the serial connection and return the active port."""
        if serial is None:
            raise RuntimeError(
                "pyserial is not installed. Install with: pip3 install pyserial"
            )

        if self._serial and self._serial.is_open:
            return self._serial.port

        active_port = self.port or self.detect_port()
        if not active_port:
            raise RuntimeError("No LiDAR USB serial device found (/dev/ttyUSB* or /dev/ttyACM*).")

        try:
            self._serial = serial.Serial(active_port, self.baudrate, timeout=self.timeout)
        except SerialException as exc:
            exc_text = str(exc)
            if "Permission denied" in exc_text:
                raise RuntimeError(
                    "Failed to open LiDAR port "
                    f"{active_port} at {self.baudrate} baud: {exc}. "
                    f"Runtime info: euid={os.geteuid()} python={os.path.realpath(os.sys.executable)} "
                    f"port={self._format_device_permissions(active_port)}"
                ) from exc
            raise RuntimeError(
                f"Failed to open LiDAR port {active_port} at {self.baudrate} baud: {exc}"
            ) from exc

        self.port = active_port
        return active_port

    def disconnect(self):
        """Stop reading and close the serial connection."""
        self.stop()
        if self._serial and self._serial.is_open:
            self._serial.close()

    def start(self, on_measurement: Optional[Callable[[LidarMeasurement], None]] = None):
        """Start background reading from the LiDAR stream."""
        self.connect()
        if self._running:
            return

        self._on_measurement = on_measurement
        self._running = True
        self._thread = Thread(target=self._read_loop, name="usb-lidar-reader", daemon=True)
        self._thread.start()

    def stop(self):
        """Stop background reading thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    @property
    def is_running(self) -> bool:
        """True while the reader thread is running."""
        return self._running

    def clear_buffer(self):
        """Discard all stored samples."""
        with self._lock:
            self._buffer.clear()

    def get_latest_measurement(self) -> Optional[LidarMeasurement]:
        """Return the newest parsed measurement, if available."""
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_measurements_snapshot(self) -> List[LidarMeasurement]:
        """Return a copy of the current buffered samples."""
        with self._lock:
            return list(self._buffer)

    def _append_measurement(self, measurement: LidarMeasurement):
        with self._lock:
            self._buffer.append(measurement)
            if len(self._buffer) > self.max_buffer_size:
                self._buffer = self._buffer[-self.max_buffer_size :]

    def _read_loop(self):
        while self._running:
            if not self._serial or not self._serial.is_open:
                break
            try:
                raw = self._serial.readline()
            except SerialException:
                break

            if not raw:
                continue

            line = raw.decode("utf-8", errors="ignore").strip()
            measurement = self._parse_line(line)
            if not measurement:
                continue

            self._append_measurement(measurement)
            if self._on_measurement:
                self._on_measurement(measurement)

        self._running = False

    @staticmethod
    def _parse_line(line: str) -> Optional[LidarMeasurement]:
        """Parse a line into a measurement.

        Supported input formats:
        - CSV: angle,distance[,quality]
        - Key/value: angle:12.3 distance:456 q:90
        """
        if not line:
            return None

        if "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 2:
                try:
                    angle = float(parts[0])
                    distance = float(parts[1])
                    quality = int(parts[2]) if len(parts) >= 3 else None
                    return LidarMeasurement(time.time(), angle, distance, quality)
                except ValueError:
                    return None

        angle_match = re.search(r"(?:angle|a)\s*[:=]\s*(-?\d+(?:\.\d+)?)", line, re.IGNORECASE)
        dist_match = re.search(
            r"(?:distance|dist|d)\s*[:=]\s*(-?\d+(?:\.\d+)?)", line, re.IGNORECASE
        )
        qual_match = re.search(r"(?:quality|q)\s*[:=]\s*(\d+)", line, re.IGNORECASE)

        if not angle_match or not dist_match:
            return None

        angle = float(angle_match.group(1))
        distance = float(dist_match.group(1))
        quality = int(qual_match.group(1)) if qual_match else None
        return LidarMeasurement(time.time(), angle, distance, quality)

    @staticmethod
    def _format_device_permissions(device_path: str) -> str:
        """Return concise owner/group/mode info for a serial device path."""
        try:
            st = os.stat(device_path)
            owner = pwd.getpwuid(st.st_uid).pw_name
            group = grp.getgrgid(st.st_gid).gr_name
            mode = oct(st.st_mode & 0o777)
            return f"{device_path} owner={owner} group={group} mode={mode}"
        except OSError as err:
            return f"{device_path} stat-error={err}"

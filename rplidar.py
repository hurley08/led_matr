
"""rplidar_a1.py - Minimal SLAMTEC RPLIDAR A1 driver over raw pyserial.

Written because the `rplidar` package on PyPI is unmaintained and the
descriptor-read path is broken on recent Python versions. This module
speaks the SLAMTEC serial protocol directly.

Verified on macOS / Python 3.14 / RPLIDAR A1M8, firmware 1.29.

Quick start
-----------
    from rplidar_a1 import RPLidarA1

    with RPLidarA1('/dev/cu.usbserial-0001') as lidar:
        print(lidar.get_info())
        print(lidar.get_health())
        for scan in lidar.iter_scans(max_scans=5):
            print(f'{len(scan)} points, first={scan[0]}')

Each scan yielded by `iter_scans` is a list of `(quality, angle_deg,
distance_mm)` tuples covering roughly one full revolution. Points with
zero quality or zero distance are dropped.
"""

from __future__ import annotations

import struct
import time
from collections import namedtuple
from typing import Iterator, List, Tuple

import serial


# --- Protocol constants ----------------------------------------------------

SYNC1 = 0xA5
SYNC2 = 0x5A

CMD_STOP        = 0x25
CMD_RESET       = 0x40
CMD_SCAN        = 0x20
CMD_FORCE_SCAN  = 0x21
CMD_GET_INFO    = 0x50
CMD_GET_HEALTH  = 0x52

DTYPE_INFO   = 0x04
DTYPE_HEALTH = 0x06
DTYPE_SCAN   = 0x81

DESCRIPTOR_LEN = 7

DeviceInfo = namedtuple(
    'DeviceInfo',
    'model firmware_major firmware_minor hardware serialnumber',
)
DeviceHealth = namedtuple('DeviceHealth', 'status error_code')

ScanPoint = Tuple[int, float, float]   # (quality, angle_deg, distance_mm)


class RPLidarError(Exception):
    pass


# --- Driver ----------------------------------------------------------------

class RPLidarA1:
    """Driver for the SLAMTEC RPLIDAR A1 (115200 baud, fixed)."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: serial.Serial | None = None

    # context-manager sugar
    def __enter__(self) -> 'RPLidarA1':
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.stop()
        except Exception:
            pass
        self.disconnect()

    # --- connection ----------------------------------------------------

    def connect(self) -> None:
        s = serial.Serial()
        s.port = self.port
        s.baudrate = self.baudrate
        s.timeout = self.timeout
        s.dsrdtr = False
        s.rtscts = False
        s.open()
        s.dtr = False
        s.rts = False
        time.sleep(0.1)
        s.reset_input_buffer()
        self._serial = s

    def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    @property
    def serial_port(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise RPLidarError('not connected; call connect() first')
        return self._serial

    # --- low-level protocol -------------------------------------------

    def _send_cmd(self, cmd: int, payload: bytes | None = None) -> None:
        s = self.serial_port
        if payload is None:
            s.write(bytes([SYNC1, cmd]))
        else:
            size = len(payload)
            checksum = SYNC1 ^ cmd ^ size
            for b in payload:
                checksum ^= b
            s.write(bytes([SYNC1, cmd, size]) + bytes(payload) + bytes([checksum]))

    def _read_descriptor(self) -> Tuple[int, int, int]:
        d = self.serial_port.read(DESCRIPTOR_LEN)
        if len(d) != DESCRIPTOR_LEN:
            raise RPLidarError(
                f'descriptor short: got {len(d)} bytes ({d.hex() or "empty"}); '
                'is the LIDAR powered and the cable seated?'
            )
        if d[0] != SYNC1 or d[1] != SYNC2:
            raise RPLidarError(f'bad descriptor sync: {d.hex()}')
        size_word = struct.unpack('<I', d[2:6])[0]
        size = size_word & 0x3FFFFFFF
        mode = size_word >> 30
        dtype = d[6]
        return size, mode, dtype

    def _read_payload(self, n: int) -> bytes:
        data = self.serial_port.read(n)
        if len(data) != n:
            raise RPLidarError(f'payload short: got {len(data)} of {n}')
        return data

    # --- commands -----------------------------------------------------

    def get_info(self) -> DeviceInfo:
        self.serial_port.reset_input_buffer()
        self._send_cmd(CMD_GET_INFO)
        size, mode, dtype = self._read_descriptor()
        if (size, mode, dtype) != (20, 0, DTYPE_INFO):
            raise RPLidarError(
                f'unexpected info descriptor: size={size} mode={mode} type=0x{dtype:02x}'
            )
        data = self._read_payload(20)
        return DeviceInfo(
            model=data[0],
            firmware_minor=data[1],
            firmware_major=data[2],
            hardware=data[3],
            serialnumber=data[4:].hex(),
        )

    def get_health(self) -> DeviceHealth:
        self.serial_port.reset_input_buffer()
        self._send_cmd(CMD_GET_HEALTH)
        size, mode, dtype = self._read_descriptor()
        if (size, mode, dtype) != (3, 0, DTYPE_HEALTH):
            raise RPLidarError(
                f'unexpected health descriptor: size={size} mode={mode} type=0x{dtype:02x}'
            )
        data = self._read_payload(3)
        status_names = {0: 'Good', 1: 'Warning', 2: 'Error'}
        return DeviceHealth(
            status=status_names.get(data[0], f'Unknown({data[0]})'),
            error_code=data[1] | (data[2] << 8),
        )

    def stop(self) -> None:
        """Stop any active scan. No reply expected."""
        if self._serial is None or not self._serial.is_open:
            return
        self._send_cmd(CMD_STOP)
        time.sleep(0.5)   # A1 needs time to fully stop streaming
        self._serial.reset_input_buffer()

    def reset(self) -> None:
        """Soft-reset the LIDAR. Takes ~2 seconds."""
        self._send_cmd(CMD_RESET)
        time.sleep(2.0)
        self.serial_port.reset_input_buffer()

    # --- scanning -----------------------------------------------------

    def start_scan(self) -> None:
        self.serial_port.reset_input_buffer()
        self._send_cmd(CMD_SCAN)
        size, mode, dtype = self._read_descriptor()
        if (size, mode, dtype) != (5, 1, DTYPE_SCAN):
            raise RPLidarError(
                f'unexpected scan descriptor: size={size} mode={mode} type=0x{dtype:02x}'
            )

    def iter_measurements(self) -> Iterator[Tuple[bool, int, float, float]]:
        """Yield raw measurements: (start_of_scan, quality, angle_deg, distance_mm).

        `start_of_scan` is True on the first measurement of each new revolution.
        Caller is responsible for having called `start_scan()` first.
        """
        s = self.serial_port
        while True:
            packet = s.read(5)
            if len(packet) != 5:
                # read timeout — try again
                continue
            b0, b1, b2, b3, b4 = packet
            start = b0 & 0x01
            inv_start = (b0 >> 1) & 0x01
            check = b1 & 0x01
            if start == inv_start or check != 1:
                # framing error — drop a byte and try to resync
                s.read(1)
                continue
            quality = b0 >> 2
            angle_q6 = (b1 >> 1) | (b2 << 7)
            distance_q2 = b3 | (b4 << 8)
            yield bool(start), quality, angle_q6 / 64.0, distance_q2 / 4.0

    def iter_scans(
        self,
        max_scans: int | None = None,
        min_points: int = 10,
    ) -> Iterator[List[ScanPoint]]:
        """Yield full revolutions as lists of (quality, angle_deg, distance_mm).

        Points with zero quality or zero distance are filtered out.
        Partial scans shorter than `min_points` are discarded.
        """
        self.start_scan()
        scan: List[ScanPoint] = []
        yielded = 0
        try:
            for is_start, quality, angle, distance in self.iter_measurements():
                if is_start and scan:
                    if len(scan) >= min_points:
                        yield scan
                        yielded += 1
                        if max_scans is not None and yielded >= max_scans:
                            return
                    scan = []
                if quality > 0 and distance > 0:
                    scan.append((quality, angle, distance))
        finally:
            self.stop()


# --- demo -----------------------------------------------------------------

if __name__ == '__main__':
    import sys

    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbserial-0001'
    with RPLidarA1(port) as lidar:
        info = lidar.get_info()
        print(
            f'Info: model=0x{info.model:02x} '
            f'fw={info.firmware_major}.{info.firmware_minor:02d} '
            f'hw={info.hardware} sn={info.serialnumber}'
        )
        print(f'Health: {lidar.get_health()}')
        print('Streaming 60 scans...')
        for i, scan in enumerate(lidar.iter_scans(max_scans=60)):
            angles = [p[1] for p in scan]
            dists = [p[2] for p in scan]
            print(
                f'  Scan {i}: {len(scan):4d} pts, '
                f'angle {min(angles):6.1f}-{max(angles):6.1f}°, '
                f'dist {min(dists):6.0f}-{max(dists):6.0f} mm'
            )

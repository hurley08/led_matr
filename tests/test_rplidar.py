"""
test_rplidar.py — verifies correct usage of the rplidar library.

Tests cover:
- _RPLidarSource opens the right serial port
- Driver connects and starts the motor on construction
- iter_scans() is used to obtain the scan iterator
- Raw scan tuples (quality, angle, distance) are converted to Point objects
- stop() calls stop(), stop_motor(), disconnect() in the correct order
- build_streams(mock=False) passes the port argument through to RPLidarA1
"""

import sys
from unittest.mock import MagicMock, call, patch

import pytest

from streams import Point, SectorStats, _MockLidarSource, _analyze, build_streams


# ── _RPLidarSource ────────────────────────────────────────────────────────────────

class TestRPLidarSource:
    """
    All tests patch rplidar into sys.modules so _RPLidarSource can import it
    without hardware being present.
    """

    def _make_source(self, mock_rplidar_mod, port="/dev/ttyUSB0"):
        """Instantiate _RPLidarSource with a mocked rplidar module."""
        from streams import _RPLidarSource
        with (
            patch.dict(sys.modules, {"rplidar": mock_rplidar_mod}),
            patch("time.sleep"),
        ):
            src = _RPLidarSource(port)
        return src, mock_rplidar_mod

    def _mock_rplidar_module(self, raw_scans=None):
        """
        Build a mock rplidar module whose RPLidarA1 class returns a controllable
        instance.  raw_scans is a list of scans, each a list of
        (quality, angle, distance) tuples.
        """
        if raw_scans is None:
            raw_scans = [[(200, 45.0, 1000.0), (180, 90.0, 1500.0)]]

        mock_lidar_instance = MagicMock()
        mock_lidar_instance.iter_scans.return_value = iter(raw_scans)

        mock_mod = MagicMock()
        mock_mod.RPLidarA1.return_value = mock_lidar_instance
        return mock_mod, mock_lidar_instance

    # ── Construction ─────────────────────────────────────────────────────────────

    def test_opens_specified_port(self, step):
        step("Create a mocked RPLidarA1 driver")
        mock_mod, _ = self._mock_rplidar_module()
        step("Construct the source with /dev/ttyUSB1")
        self._make_source(mock_mod, port="/dev/ttyUSB1")
        step("Verify the driver received the specified serial port")
        mock_mod.RPLidarA1.assert_called_once_with("/dev/ttyUSB1")

    def test_uses_default_port(self, step):
        step("Create a mocked RPLidarA1 driver")
        mock_mod, _ = self._mock_rplidar_module()
        step("Construct the source without an explicit port")
        self._make_source(mock_mod)
        step("Verify the default serial port is /dev/ttyUSB0")
        mock_mod.RPLidarA1.assert_called_once_with("/dev/ttyUSB0")

    def test_connects_on_init(self, step):
        step("Create a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        step("Construct the source")
        self._make_source(mock_mod)
        step("Verify source initialization connected the driver")
        lidar_inst.connect.assert_called_once()

    def test_starts_motor_on_init(self, step):
        step("Create a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        step("Construct the source")
        self._make_source(mock_mod)
        step("Verify initialization started the lidar motor")
        lidar_inst.start_motor.assert_called_once()

    def test_calls_iter_scans_on_init(self, step):
        step("Create a mocked lidar instance with scan data")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        step("Construct the source and initialize scanning")
        self._make_source(mock_mod)
        step("Verify initialization requested the scan iterator")
        lidar_inst.iter_scans.assert_called_once()

    # ── get_scan() ────────────────────────────────────────────────────────────────

    def test_get_scan_returns_list_of_points(self, step):
        step("Prepare one raw scan containing two lidar tuples")
        raw = [[(200, 45.0, 1000.0), (180, 270.0, 800.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        step("Construct the source with the prepared scan")
        src, _ = self._make_source(mock_mod)

        step("Read and convert the next scan")
        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        step("Verify two Point objects were returned")
        assert isinstance(pts, list)
        assert all(isinstance(p, Point) for p in pts)
        assert len(pts) == 2

    def test_get_scan_maps_angle_correctly(self, step):
        step("Prepare a raw tuple with angle 123.5 degrees")
        raw = [[(150, 123.5, 500.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        step("Convert the raw scan to application points")
        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        step("Verify tuple element 1 maps to Point.angle")
        assert pts[0].angle == pytest.approx(123.5)

    def test_get_scan_maps_distance_correctly(self, step):
        step("Prepare a raw tuple with distance 2345.6 mm")
        raw = [[(150, 0.0, 2345.6)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        step("Convert the raw scan to application points")
        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        step("Verify tuple element 2 maps to Point.distance")
        assert pts[0].distance == pytest.approx(2345.6)

    def test_get_scan_maps_quality_correctly(self, step):
        step("Prepare a raw tuple with quality 47")
        raw = [[(47, 90.0, 1000.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        step("Convert the raw scan to application points")
        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        step("Verify tuple element 0 maps to Point.quality")
        assert pts[0].quality == 47

    def test_get_scan_tuple_order_is_quality_angle_distance(self, step):
        """rplidar yields (quality, angle, distance) — verify the mapping is not swapped."""
        step("Prepare a tuple with distinct quality, angle, and distance values")
        raw = [[(10, 45.0, 999.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        step("Convert the tuple into a Point")
        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        step("Verify all three tuple positions map to the correct fields")
        p = pts[0]
        assert p.quality  == 10
        assert p.angle    == pytest.approx(45.0)
        assert p.distance == pytest.approx(999.0)

    # ── stop() ────────────────────────────────────────────────────────────────────

    def test_stop_calls_stop_on_lidar(self, step):
        step("Construct a source around a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        step("Stop the source")
        src.stop()
        step("Verify scanning was stopped")
        lidar_inst.stop.assert_called_once()

    def test_stop_calls_stop_motor(self, step):
        step("Construct a source around a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        step("Stop the source")
        src.stop()
        step("Verify the motor was stopped")
        lidar_inst.stop_motor.assert_called_once()

    def test_stop_calls_disconnect(self, step):
        step("Construct a source around a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        step("Stop the source")
        src.stop()
        step("Verify the serial driver disconnected")
        lidar_inst.disconnect.assert_called_once()

    def test_stop_sequence_is_stop_then_stop_motor_then_disconnect(self, step):
        """Order matters: stop scanning before stopping motor before disconnecting."""
        step("Construct a source around a mocked lidar instance")
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)

        step("Attach an ordered call recorder to shutdown methods")
        manager = MagicMock()
        lidar_inst.stop.side_effect        = lambda: manager.stop()
        lidar_inst.stop_motor.side_effect  = lambda: manager.stop_motor()
        lidar_inst.disconnect.side_effect  = lambda: manager.disconnect()

        step("Stop the source")
        src.stop()

        step("Verify scan, motor, and connection shutdown order")
        assert manager.mock_calls == [
            call.stop(),
            call.stop_motor(),
            call.disconnect(),
        ]


# ── build_streams(mock=False) ─────────────────────────────────────────────────────

class TestBuildStreamsReal:
    def test_real_source_passes_port_to_rplidar(self, step):
        step("Create a mocked driver module with valid scan data")
        mock_mod, _ = TestRPLidarSource()._mock_rplidar_module()

        step("Build real-mode streams for /dev/ttyUSB2")
        with (
            patch.dict(sys.modules, {"rplidar": mock_mod}),
            patch("time.sleep"),
        ):
            scan_s, _ = build_streams(mock=False, port="/dev/ttyUSB2")

        step("Verify RPLidarA1 received the requested port")
        mock_mod.RPLidarA1.assert_called_once_with("/dev/ttyUSB2")

    def test_real_source_starts_motor(self, step):
        step("Create a mocked lidar instance")
        mock_mod, lidar_inst = TestRPLidarSource()._mock_rplidar_module()

        step("Build streams in real hardware mode")
        with (
            patch.dict(sys.modules, {"rplidar": mock_mod}),
            patch("time.sleep"),
        ):
            build_streams(mock=False)

        step("Verify stream construction started the motor")
        lidar_inst.start_motor.assert_called_once()


# ── _MockLidarSource ──────────────────────────────────────────────────────────────

class TestMockLidarSource:
    def test_returns_list_of_points(self, step):
        step("Create the deterministic mock lidar source")
        src = _MockLidarSource()
        step("Generate one synthetic scan")
        pts = src.get_scan()
        step("Verify the scan is a list of Point objects")
        assert isinstance(pts, list)
        assert all(isinstance(p, Point) for p in pts)

    def test_angles_span_full_circle(self, step):
        step("Generate one deterministic synthetic scan")
        src  = _MockLidarSource()
        pts  = src.get_scan()
        step("Collect all generated point angles")
        angles = [p.angle for p in pts]
        step("Verify angles stay within a full 0 to 360 degree revolution")
        assert min(angles) >= 0
        assert max(angles) < 360

    def test_distances_are_positive(self, step):
        step("Generate one deterministic synthetic scan")
        src = _MockLidarSource()
        pts = src.get_scan()
        step("Verify every generated distance is positive")
        assert all(p.distance > 0 for p in pts)

    def test_successive_scans_differ(self, step):
        """Mock advances internal time — each call returns slightly different data."""
        step("Create the deterministic mock lidar source")
        src  = _MockLidarSource()
        step("Generate two successive scans")
        pts1 = src.get_scan()
        pts2 = src.get_scan()
        step("Extract distance sequences from both scans")
        dists1 = [p.distance for p in pts1]
        dists2 = [p.distance for p in pts2]
        step("Verify simulated motion changes successive distance readings")
        assert dists1 != dists2


# ── _analyze() ────────────────────────────────────────────────────────────────────

class TestAnalyze:
    def _make_points(self, angle_dist_pairs):
        return [Point(angle=a, distance=d, quality=200)
                for a, d in angle_dist_pairs]

    def test_front_sector_minimum(self, step):
        step("Create points inside and outside the rotated front sector")
        pts  = self._make_points([(0, 100), (180, 300), (200, 800)])
        step("Analyze sector statistics")
        stat = _analyze(pts)
        step("Verify front reports the minimum distance from 135 to 225 degrees")
        assert stat.front == pytest.approx(300)

    def test_left_sector_minimum(self, step):
        step("Create points inside and outside the left sector")
        pts  = self._make_points([(270, 500), (280, 900), (90, 100)])
        step("Analyze sector statistics")
        stat = _analyze(pts)
        step("Verify left reports the minimum distance from 225 to 315 degrees")
        assert stat.left == pytest.approx(500)

    def test_right_sector_minimum(self, step):
        step("Create points inside and outside the right sector")
        pts  = self._make_points([(60, 400), (100, 700), (270, 100)])
        step("Analyze sector statistics")
        stat = _analyze(pts)
        step("Verify right reports the minimum distance from 45 to 135 degrees")
        assert stat.right == pytest.approx(400)

    def test_global_minimum(self, step):
        step("Create valid points with different distances")
        pts  = self._make_points([(0, 1000), (90, 200), (180, 500)])
        step("Analyze global scan statistics")
        stat = _analyze(pts)
        step("Verify the smallest distance is reported globally")
        assert stat.min_dist == pytest.approx(200)

    def test_average_distance(self, step):
        step("Create two valid points at 1000 and 2000 mm")
        pts  = self._make_points([(0, 1000), (180, 2000)])
        step("Analyze global scan statistics")
        stat = _analyze(pts)
        step("Verify the arithmetic mean is 1500 mm")
        assert stat.avg_dist == pytest.approx(1500)

    def test_zero_quality_points_excluded(self, step):
        step("Create one zero-quality point and one valid point")
        pts = [
            Point(angle=0,   distance=100, quality=0),    # bad — excluded
            Point(angle=180, distance=2000, quality=200),  # good
        ]
        step("Analyze the scan")
        stat = _analyze(pts)
        step("Verify the zero-quality point does not affect the minimum")
        assert stat.min_dist == pytest.approx(2000)

    def test_empty_scan_returns_sentinel_values(self, step):
        step("Analyze an empty scan")
        stat = _analyze([])
        step("Verify distance fields use sentinel values")
        assert stat.front    == 9999
        assert stat.min_dist == 9999
        step("Verify density and health report zero")
        assert stat.density  == 0
        assert stat.health   == 0

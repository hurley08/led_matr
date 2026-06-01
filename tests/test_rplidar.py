"""
test_rplidar.py — verifies correct usage of the rplidar library.

Tests cover:
- _RPLidarSource opens the right serial port
- Motor is started on construction
- iter_scans() is used to obtain the scan iterator
- Raw scan tuples (quality, angle, distance) are converted to Point objects
- stop() calls stop(), stop_motor(), disconnect() in the correct order
- build_streams(mock=False) passes the port argument through to RPLidar
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
        with patch.dict(sys.modules, {"rplidar": mock_rplidar_mod}):
            src = _RPLidarSource(port)
        return src, mock_rplidar_mod

    def _mock_rplidar_module(self, raw_scans=None):
        """
        Build a mock rplidar module whose RPLidar class returns a controllable
        instance.  raw_scans is a list of scans, each a list of
        (quality, angle, distance) tuples.
        """
        if raw_scans is None:
            raw_scans = [[(200, 45.0, 1000.0), (180, 90.0, 1500.0)]]

        mock_lidar_instance = MagicMock()
        mock_lidar_instance.iter_scans.return_value = iter(raw_scans)

        mock_mod = MagicMock()
        mock_mod.RPLidar.return_value = mock_lidar_instance
        return mock_mod, mock_lidar_instance

    # ── Construction ─────────────────────────────────────────────────────────────

    def test_opens_specified_port(self):
        mock_mod, _ = self._mock_rplidar_module()
        self._make_source(mock_mod, port="/dev/ttyUSB1")
        mock_mod.RPLidar.assert_called_once_with("/dev/ttyUSB1")

    def test_uses_default_port(self):
        mock_mod, _ = self._mock_rplidar_module()
        self._make_source(mock_mod)
        mock_mod.RPLidar.assert_called_once_with("/dev/ttyUSB0")

    def test_starts_motor_on_init(self):
        mock_mod, lidar_inst = self._mock_rplidar_module()
        self._make_source(mock_mod)
        lidar_inst.start_motor.assert_called_once()

    def test_calls_iter_scans_on_init(self):
        mock_mod, lidar_inst = self._mock_rplidar_module()
        self._make_source(mock_mod)
        lidar_inst.iter_scans.assert_called_once()

    # ── get_scan() ────────────────────────────────────────────────────────────────

    def test_get_scan_returns_list_of_points(self):
        raw = [[(200, 45.0, 1000.0), (180, 270.0, 800.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        assert isinstance(pts, list)
        assert all(isinstance(p, Point) for p in pts)
        assert len(pts) == 2

    def test_get_scan_maps_angle_correctly(self):
        raw = [[(150, 123.5, 500.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        assert pts[0].angle == pytest.approx(123.5)

    def test_get_scan_maps_distance_correctly(self):
        raw = [[(150, 0.0, 2345.6)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        assert pts[0].distance == pytest.approx(2345.6)

    def test_get_scan_maps_quality_correctly(self):
        raw = [[(47, 90.0, 1000.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        assert pts[0].quality == 47

    def test_get_scan_tuple_order_is_quality_angle_distance(self):
        """rplidar yields (quality, angle, distance) — verify the mapping is not swapped."""
        raw = [[(10, 45.0, 999.0)]]
        mock_mod, _ = self._mock_rplidar_module(raw_scans=raw)
        src, _ = self._make_source(mock_mod)

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            pts = src.get_scan()

        p = pts[0]
        assert p.quality  == 10
        assert p.angle    == pytest.approx(45.0)
        assert p.distance == pytest.approx(999.0)

    # ── stop() ────────────────────────────────────────────────────────────────────

    def test_stop_calls_stop_on_lidar(self):
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        src.stop()
        lidar_inst.stop.assert_called_once()

    def test_stop_calls_stop_motor(self):
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        src.stop()
        lidar_inst.stop_motor.assert_called_once()

    def test_stop_calls_disconnect(self):
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)
        src.stop()
        lidar_inst.disconnect.assert_called_once()

    def test_stop_sequence_is_stop_then_stop_motor_then_disconnect(self):
        """Order matters: stop scanning before stopping motor before disconnecting."""
        mock_mod, lidar_inst = self._mock_rplidar_module()
        src, _ = self._make_source(mock_mod)

        manager = MagicMock()
        lidar_inst.stop.side_effect        = lambda: manager.stop()
        lidar_inst.stop_motor.side_effect  = lambda: manager.stop_motor()
        lidar_inst.disconnect.side_effect  = lambda: manager.disconnect()

        src.stop()

        assert manager.mock_calls == [
            call.stop(),
            call.stop_motor(),
            call.disconnect(),
        ]


# ── build_streams(mock=False) ─────────────────────────────────────────────────────

class TestBuildStreamsReal:
    def test_real_source_passes_port_to_rplidar(self):
        mock_mod, lidar_inst = MagicMock(), MagicMock()
        lidar_inst.iter_scans.return_value = iter([])
        mock_mod.RPLidar.return_value = lidar_inst

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            scan_s, _ = build_streams(mock=False, port="/dev/ttyUSB2")

        mock_mod.RPLidar.assert_called_once_with("/dev/ttyUSB2")

    def test_real_source_starts_motor(self):
        mock_mod, lidar_inst = MagicMock(), MagicMock()
        lidar_inst.iter_scans.return_value = iter([])
        mock_mod.RPLidar.return_value = lidar_inst

        with patch.dict(sys.modules, {"rplidar": mock_mod}):
            build_streams(mock=False)

        lidar_inst.start_motor.assert_called_once()


# ── _MockLidarSource ──────────────────────────────────────────────────────────────

class TestMockLidarSource:
    def test_returns_list_of_points(self):
        src = _MockLidarSource()
        pts = src.get_scan()
        assert isinstance(pts, list)
        assert all(isinstance(p, Point) for p in pts)

    def test_angles_span_full_circle(self):
        src  = _MockLidarSource()
        pts  = src.get_scan()
        angles = [p.angle for p in pts]
        assert min(angles) >= 0
        assert max(angles) < 360

    def test_distances_are_positive(self):
        src = _MockLidarSource()
        pts = src.get_scan()
        assert all(p.distance > 0 for p in pts)

    def test_successive_scans_differ(self):
        """Mock advances internal time — each call returns slightly different data."""
        src  = _MockLidarSource()
        pts1 = src.get_scan()
        pts2 = src.get_scan()
        dists1 = [p.distance for p in pts1]
        dists2 = [p.distance for p in pts2]
        assert dists1 != dists2


# ── _analyze() ────────────────────────────────────────────────────────────────────

class TestAnalyze:
    def _make_points(self, angle_dist_pairs):
        return [Point(angle=a, distance=d, quality=200)
                for a, d in angle_dist_pairs]

    def test_front_sector_minimum(self):
        pts  = self._make_points([(0, 300), (10, 800), (180, 100)])
        stat = _analyze(pts)
        assert stat.front == pytest.approx(300)

    def test_left_sector_minimum(self):
        pts  = self._make_points([(270, 500), (280, 900), (90, 100)])
        stat = _analyze(pts)
        assert stat.left == pytest.approx(500)

    def test_right_sector_minimum(self):
        pts  = self._make_points([(60, 400), (100, 700), (270, 100)])
        stat = _analyze(pts)
        assert stat.right == pytest.approx(400)

    def test_global_minimum(self):
        pts  = self._make_points([(0, 1000), (90, 200), (180, 500)])
        stat = _analyze(pts)
        assert stat.min_dist == pytest.approx(200)

    def test_average_distance(self):
        pts  = self._make_points([(0, 1000), (180, 2000)])
        stat = _analyze(pts)
        assert stat.avg_dist == pytest.approx(1500)

    def test_zero_quality_points_excluded(self):
        pts = [
            Point(angle=0,   distance=100, quality=0),    # bad — excluded
            Point(angle=180, distance=2000, quality=200),  # good
        ]
        stat = _analyze(pts)
        assert stat.min_dist == pytest.approx(2000)

    def test_empty_scan_returns_sentinel_values(self):
        stat = _analyze([])
        assert stat.front    == 9999
        assert stat.min_dist == 9999
        assert stat.density  == 0
        assert stat.health   == 0

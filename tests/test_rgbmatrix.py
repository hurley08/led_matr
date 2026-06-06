"""
test_rgbmatrix.py — verifies correct usage of the rgbmatrix library.

Tests cover:
- PanelView correctly applies the panel x-offset when calling SetPixel
- PanelView silently ignores coordinates outside the 64×64 boundary
- Runtime.run() creates a canvas, renders into it, and calls SwapOnVSync
- Runtime.run() clears each panel before calling render()
- create_matrix() configures RGBMatrixOptions with the expected hardware settings
"""

from unittest.mock import MagicMock, call, patch

import pytest

from core import Panel, PanelView, Runtime, Stream, Visualization


# ── PanelView ────────────────────────────────────────────────────────────────────

class TestPanelView:
    def test_left_panel_passes_x_unchanged(self, spy_canvas, step):
        step("Create a view for the left panel at offset 0")
        view = PanelView(spy_canvas, Panel.LEFT.value)   # offset = 0
        step("Draw a red pixel at local coordinate (5, 10)")
        view.set_pixel(5, 10, 255, 0, 0)
        step("Verify the pixel remains at physical coordinate (5, 10)")
        assert spy_canvas.get(5, 10) == (255, 0, 0)

    def test_right_panel_adds_64_to_x(self, spy_canvas, step):
        step("Create a view for the right panel at offset 64")
        view = PanelView(spy_canvas, Panel.RIGHT.value)  # offset = 64
        step("Draw a green pixel at local coordinate (0, 0)")
        view.set_pixel(0, 0, 0, 255, 0)
        step("Verify the pixel is written at physical coordinate (64, 0)")
        assert spy_canvas.get(64, 0) == (0, 255, 0)

    def test_right_panel_corner_pixel(self, spy_canvas, step):
        step("Create a view for the right panel")
        view = PanelView(spy_canvas, Panel.RIGHT.value)
        step("Draw a blue pixel at the panel's lower-right corner")
        view.set_pixel(63, 63, 0, 0, 255)
        step("Verify the corner maps to physical coordinate (127, 63)")
        assert spy_canvas.get(127, 63) == (0, 0, 255)

    def test_negative_x_is_ignored(self, spy_canvas, step):
        step("Create a view for the left panel")
        view = PanelView(spy_canvas, Panel.LEFT.value)
        step("Attempt to draw at negative x coordinate -1")
        view.set_pixel(-1, 0, 255, 255, 255)
        step("Verify no canvas pixel was lit")
        assert not spy_canvas.any_lit()

    def test_x_out_of_right_edge_is_ignored(self, spy_canvas, step):
        step("Create a view for the left panel")
        view = PanelView(spy_canvas, Panel.LEFT.value)
        step("Attempt to draw one pixel beyond the panel's right edge")
        view.set_pixel(64, 0, 255, 255, 255)
        step("Verify no canvas pixel was lit")
        assert not spy_canvas.any_lit()

    def test_y_out_of_bottom_edge_is_ignored(self, spy_canvas, step):
        step("Create a view for the left panel")
        view = PanelView(spy_canvas, Panel.LEFT.value)
        step("Attempt to draw one pixel below the panel")
        view.set_pixel(0, 64, 255, 255, 255)
        step("Verify no canvas pixel was lit")
        assert not spy_canvas.any_lit()

    def test_fill_rect_covers_exact_bounds(self, spy_canvas, step):
        step("Create a view for the left panel")
        view = PanelView(spy_canvas, Panel.LEFT.value)
        step("Fill the inclusive rectangle from (10, 20) through (12, 22)")
        view.fill_rect(10, 20, 12, 22, 100, 150, 200)
        step("Verify every pixel inside the rectangle has the requested color")
        for x in range(10, 13):
            for y in range(20, 23):
                assert spy_canvas.get(x, y) == (100, 150, 200), \
                    f"pixel ({x},{y}) not set"
        # One pixel outside the rect should be black
        step("Verify the adjacent pixel outside the rectangle remains black")
        assert spy_canvas.get(13, 20) == (0, 0, 0)

    def test_fill_rect_with_right_panel_offset(self, spy_canvas, step):
        step("Create a view for the right panel")
        view = PanelView(spy_canvas, Panel.RIGHT.value)
        step("Fill a 2 by 2 rectangle at the right panel's local origin")
        view.fill_rect(0, 0, 1, 1, 255, 0, 0)
        step("Verify the rectangle starts at physical x coordinate 64")
        assert spy_canvas.get(64, 0) == (255, 0, 0)
        assert spy_canvas.get(65, 1) == (255, 0, 0)

    def test_clear_blacks_out_panel(self, spy_canvas, step):
        step("Create a view and light one pixel on the left panel")
        view = PanelView(spy_canvas, Panel.LEFT.value)
        view.set_pixel(5, 5, 255, 255, 255)
        step("Clear the panel view")
        view.clear()
        # clear() overwrites every cell — the previously lit pixel becomes black
        step("Verify the previously lit pixel is black")
        assert spy_canvas.get(5, 5) == (0, 0, 0)


# ── Runtime × rgbmatrix ──────────────────────────────────────────────────────────

class _CountingViz(Visualization):
    """Records how many times render() was called and what data it received."""
    panel   = Panel.LEFT
    streams = ["test.data"]

    def __init__(self):
        self.render_calls = []

    def render(self, view, *, test_data, **_):
        self.render_calls.append(test_data)
        view.set_pixel(0, 0, 255, 255, 255)   # mark that we ran


class TestRuntimeRgbmatrix:
    def _make_rt(self):
        stream = Stream("test.data", "test stream", lambda: [1, 2, 3])
        viz    = _CountingViz()
        rt     = Runtime().add_stream(stream).add_visualization(viz)
        return rt, viz

    def test_run_creates_frame_canvas(self, mock_matrix, step):
        step("Build a runtime with one stream and visualization")
        rt, _ = self._make_rt()
        step("Run one rendered frame using the mocked matrix")
        rt.run(mock_matrix)
        step("Verify the runtime requested exactly one frame canvas")
        mock_matrix.CreateFrameCanvas.assert_called_once()

    def test_run_calls_swap_on_vsync(self, mock_matrix, spy_canvas, step):
        step("Build and run a runtime using the spy canvas")
        rt, _ = self._make_rt()
        rt.run(mock_matrix)
        # SwapOnVSync should have been called with the canvas from CreateFrameCanvas
        step("Verify the rendered spy canvas was submitted on vertical sync")
        mock_matrix.SwapOnVSync.assert_called_with(spy_canvas)

    def test_run_calls_matrix_clear_on_keyboard_interrupt(self, mock_matrix, step):
        step("Build a runtime whose mocked matrix interrupts after one frame")
        rt, _ = self._make_rt()
        step("Run until the simulated KeyboardInterrupt triggers shutdown")
        rt.run(mock_matrix)
        step("Verify shutdown cleared the physical matrix")
        mock_matrix.Clear.assert_called_once()

    def test_run_invokes_visualization_render(self, mock_matrix, step):
        step("Build a runtime with a counting visualization")
        rt, viz = self._make_rt()
        step("Run one or more frames")
        rt.run(mock_matrix)
        step("Verify the visualization rendered at least once")
        assert len(viz.render_calls) >= 1

    def test_run_passes_stream_data_to_visualization(self, mock_matrix, step):
        step("Build a runtime whose stream returns [1, 2, 3]")
        rt, viz = self._make_rt()
        step("Run a frame and capture visualization inputs")
        rt.run(mock_matrix)
        step("Verify stream data reached the visualization unchanged")
        assert viz.render_calls[0] == [1, 2, 3]

    def test_run_clears_panel_before_each_render(
        self, mock_matrix, spy_canvas, step
    ):
        """
        After clear() every pixel in the panel should start as (0,0,0).
        We verify this by checking that a pixel set in frame N is gone in
        frame N+1 (the clear happens before render, not after).
        """
        step("Configure a visualization that records its starting pixel")
        frame = {"n": 0}
        pixels_at_start = {}

        class _PixelWatcher(Visualization):
            panel   = Panel.LEFT
            streams = ["test.data"]

            def render(self, view, **_):
                pixels_at_start[frame["n"]] = spy_canvas.get(0, 0)
                view.set_pixel(0, 0, 200, 200, 200)
                frame["n"] += 1

        stream = Stream("test.data", "d", lambda: None)
        rt = Runtime().add_stream(stream).add_visualization(_PixelWatcher())

        # Allow two frames before KeyboardInterrupt
        call_count = {"n": 0}
        def _swap(canvas):
            call_count["n"] += 1
            if call_count["n"] >= 3:
                raise KeyboardInterrupt
            return canvas
        mock_matrix.SwapOnVSync.side_effect = _swap

        step("Run two complete frames before simulated shutdown")
        rt.run(mock_matrix)

        # Frame 1 started with black (nothing drawn yet)
        step("Verify frame one started with a clear panel")
        assert pixels_at_start[0] == (0, 0, 0)
        # Frame 2 also started with black (panel was cleared between frames)
        step("Verify frame two also started with a clear panel")
        assert pixels_at_start[1] == (0, 0, 0)


# ── create_matrix() hardware settings ────────────────────────────────────────────

class TestCreateMatrix:
    def test_matrix_options_rows(self, step):
        from unittest.mock import patch as _patch
        import sys

        mock_rgb = MagicMock()
        captured = {}

        def _capture_options():
            opts = MagicMock()
            captured["opts"] = opts
            return opts

        mock_rgb.RGBMatrixOptions.side_effect = _capture_options

        step("Replace rgbmatrix with a mock that captures matrix options")
        with _patch.dict(sys.modules, {"rgbmatrix": mock_rgb}):
            # Re-import create_matrix with the patched module
            import importlib
            import main as _main
            importlib.reload(_main)
            try:
                step("Create a matrix using the production configuration")
                _main.create_matrix()
            except Exception:
                pass   # RGBMatrix() constructor may fail on mock — that's fine

        step("Verify the expected panel dimensions and hardware options")
        opts = captured.get("opts")
        assert opts is not None, "RGBMatrixOptions was never instantiated"
        assert opts.rows == 64
        assert opts.cols == 64
        assert opts.chain_length == 2
        assert opts.parallel == 1
        assert opts.gpio_slowdown == 4
        assert opts.brightness == 80
        assert opts.disable_hardware_pulsing is True

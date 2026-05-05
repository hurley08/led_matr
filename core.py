"""
core.py — LED matrix pub/sub framework.

Usage pattern
─────────────
1. Define streams — named data sources with a description and a callable.

    scan_stream = Stream(
        name        = "lidar.scan",
        description = "Raw point cloud from RPLidar (List[Point])",
        source      = scanner.get_scan,
    )

2. Define visualizations — declare which streams they need and implement render().

    class RadarMap(Visualization):
        panel   = Panel.LEFT
        streams = ["lidar.scan"]

        def render(self, view, *, lidar_scan, **_):
            for pt in lidar_scan:
                ...

3. Register everything with a Runtime and call run().

    rt = Runtime()
    rt.add_stream(scan_stream)
    rt.add_visualization(RadarMap())
    rt.list_streams()   # shows all streams + active visualizations
    rt.run(matrix)      # blocks; Ctrl-C to exit cleanly
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ── Panel ───────────────────────────────────────────────────────────────────────

class Panel(Enum):
    LEFT  = 0
    RIGHT = 64   # x-offset for the right panel on a 128-wide canvas


# ── PanelView ───────────────────────────────────────────────────────────────────

class PanelView:
    """
    A 64×64 view into the full matrix canvas at the panel's x-offset.

    Visualizations use local (0,0)-based coordinates; the offset is
    applied transparently.  The underlying canvas just needs SetPixel().
    """
    W = H = 64

    def __init__(self, canvas: Any, x_offset: int):
        self._canvas  = canvas
        self._x_off   = x_offset

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int):
        if 0 <= x < self.W and 0 <= y < self.H:
            self._canvas.SetPixel(x + self._x_off, y, r, g, b)

    def fill(self, r: int, g: int, b: int):
        for y in range(self.H):
            for x in range(self.W):
                self._canvas.SetPixel(x + self._x_off, y, r, g, b)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int,
                  r: int, g: int, b: int):
        for y in range(max(0, y0), min(self.H, y1 + 1)):
            for x in range(max(0, x0), min(self.W, x1 + 1)):
                self._canvas.SetPixel(x + self._x_off, y, r, g, b)

    def clear(self):
        self.fill(0, 0, 0)


# ── Stream ───────────────────────────────────────────────────────────────────────

class Stream:
    """
    A named, self-describing data source.

    Parameters
    ──────────
    name        Dot-separated identifier, e.g. "lidar.scan".
    description Human-readable summary of the data type and shape.
    source      Zero-argument callable that returns the latest value.
                For derived streams, this may reference other streams' .latest.
    depends_on  Optional list of stream names this one is derived from.
                The Runtime updates primaries first, then derived streams in
                declaration order.
    """

    def __init__(
        self,
        name:        str,
        description: str,
        source:      Callable[[], Any],
        *,
        depends_on:  Optional[List[str]] = None,
    ):
        self.name        = name
        self.description = description
        self.depends_on  = depends_on or []
        self._source     = source
        self.latest: Any = None

    def update(self):
        self.latest = self._source()

    def __repr__(self) -> str:
        dep = f"  derived from {self.depends_on}" if self.depends_on else "  primary"
        return f"Stream({self.name!r}{dep})"


# ── Visualization ────────────────────────────────────────────────────────────────

class Visualization:
    """
    Base class for panel renderers.

    Subclass, set `panel` and `streams`, then implement `render()`.

    The `render` method receives a PanelView (local 64×64 coordinate space)
    and keyword arguments named after each subscribed stream, with dots
    replaced by underscores:

        streams = ["lidar.scan", "lidar.sectors"]

        def render(self, view, *, lidar_scan, lidar_sectors, **_):
            ...

    The trailing **_ lets you ignore streams you don't use yet.
    """

    panel:   Panel      = Panel.LEFT
    streams: List[str]  = []

    def render(self, view: PanelView, **stream_data: Any):
        raise NotImplementedError

    @property
    def _kwarg_names(self) -> Dict[str, str]:
        """Map stream name → Python kwarg name (dots → underscores)."""
        return {s: s.replace(".", "_") for s in self.streams}


# ── Runtime ───────────────────────────────────────────────────────────────────────

class Runtime:
    """
    Connects streams to visualizations and drives the render loop.

    Quick reference
    ───────────────
    rt.add_stream(stream)          Register a data stream.
    rt.add_visualization(viz)      Subscribe a visualization to its streams.
    rt.list_streams()              Print all streams and active visualizations.
    rt.run(matrix)                 Start the render loop (blocks until Ctrl-C).
    """

    def __init__(self):
        self._streams: Dict[str, Stream]  = {}
        self._vizs:    List[Visualization] = []

    # ── Registration ───────────────────────────────────────────────────────────

    def add_stream(self, stream: Stream) -> "Runtime":
        self._streams[stream.name] = stream
        return self   # fluent API

    def add_visualization(self, viz: Visualization) -> "Runtime":
        missing = [s for s in viz.streams if s not in self._streams]
        if missing:
            raise ValueError(
                f"{type(viz).__name__} subscribes to unknown stream(s): {missing}\n"
                f"Registered streams: {list(self._streams)}"
            )
        self._vizs.append(viz)
        return self

    # ── Introspection ──────────────────────────────────────────────────────────

    def list_streams(self):
        """Print a human-readable summary of all streams and visualizations."""
        col = 24
        print("\nAvailable streams")
        print("─" * 72)
        primaries = [s for s in self._streams.values() if not s.depends_on]
        derived   = [s for s in self._streams.values() if s.depends_on]
        for s in primaries + derived:
            tag  = "(primary)" if not s.depends_on else f"(← {', '.join(s.depends_on)})"
            print(f"  {s.name:<{col}} {s.description}")
            print(f"  {'':<{col}} {tag}")
        print()
        print("Active visualizations")
        print("─" * 72)
        if not self._vizs:
            print("  (none)")
        for v in self._vizs:
            subs = ", ".join(v.streams) if v.streams else "—"
            print(f"  {type(v).__name__:<{col}} panel={v.panel.name:<6}  streams=[{subs}]")
        print()

    # ── Render loop ────────────────────────────────────────────────────────────

    def run(self, matrix, *, target_fps: int = 20):
        """
        Main loop.  Calls all stream sources, then renders each visualization
        into its panel.  Swaps the canvas on VSync and sleeps to hit target_fps.

        Parameters
        ──────────
        matrix      rgbmatrix.RGBMatrix instance.
        target_fps  Desired frames per second (default 20).
        """
        frame_time = 1.0 / target_fps
        canvas     = matrix.CreateFrameCanvas()

        # Split streams into primaries and derived (primaries updated first)
        primaries = [s for s in self._streams.values() if not s.depends_on]
        derived   = [s for s in self._streams.values() if s.depends_on]

        print(f"Runtime started — {len(self._streams)} stream(s), "
              f"{len(self._vizs)} visualization(s), target {target_fps} fps")

        try:
            while True:
                t0 = time.monotonic()

                # Update data
                for stream in primaries:
                    stream.update()
                for stream in derived:
                    stream.update()

                # Render
                for viz in self._vizs:
                    view  = PanelView(canvas, viz.panel.value)
                    view.clear()
                    kwargs = {
                        name.replace(".", "_"): self._streams[name].latest
                        for name in viz.streams
                    }
                    viz.render(view, **kwargs)

                canvas = matrix.SwapOnVSync(canvas)

                elapsed = time.monotonic() - t0
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)

        except KeyboardInterrupt:
            matrix.Clear()
            print("\nStopped.")

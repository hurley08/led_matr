#!/usr/bin/env python3
"""
main.py — entry point for led_matr.

Wires streams and visualizations into the Runtime and starts the render loop.

Usage
─────
    sudo python3 main.py              # real RPLidar on /dev/ttyUSB0
    sudo python3 main.py --mock       # mock data, no hardware needed
    sudo python3 main.py --port /dev/ttyUSB1
         python3 main.py --list       # show available streams, then exit
"""

import sys

from core    import Runtime
from streams import build_streams
from panels.map_panel import RadarMap
from panels.dashboard import Dashboard

# ── Configuration ────────────────────────────────────────────────────────────────

FONT_PATH  = "/home/pi4/projects/led_matr/rpi-rgb-led-matrix/fonts/5x8.bdf"
TARGET_FPS = 20

# ── Matrix setup ─────────────────────────────────────────────────────────────────

def create_matrix():
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    opts = RGBMatrixOptions()
    opts.rows                     = 64
    opts.cols                     = 64
    opts.chain_length             = 2
    opts.parallel                 = 1
    opts.hardware_mapping         = "regular"
    opts.gpio_slowdown            = 4
    opts.brightness               = 80
    opts.disable_hardware_pulsing = True
    return RGBMatrix(options=opts)

# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    args  = sys.argv[1:]
    mock  = "--mock" in args
    port  = "/dev/ttyUSB0"
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--port="):
            port = arg.split("=", 1)[1]
        elif arg == "--port" and i + 1 < len(args):
            port = args[i + 1]
            i += 1
        i += 1
    list_ = "--list" in args
    effective_mock = mock or list_

    # Build streams. In list mode, force mock streams so listing does not
    # instantiate hardware-backed sources with side effects.
    scan_stream, sector_stream = build_streams(mock=effective_mock, port=port)

    # Build runtime and register everything
    rt = (
        Runtime()
        .add_stream(scan_stream)
        .add_stream(sector_stream)
        .add_visualization(RadarMap(heading_deg=0))
        .add_visualization(Dashboard(font_path=FONT_PATH))
    )

    # Always show the stream list so the operator can see what's running
    rt.list_streams()

    if list_:
        return

    matrix = create_matrix()
    rt.run(matrix, target_fps=TARGET_FPS)


if __name__ == "__main__":
    main()

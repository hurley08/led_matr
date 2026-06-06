"""LED matrix backends.

The Raspberry Pi driver is imported only when the hardware backend is created.
This keeps the rest of the application importable and testable on any platform.
"""

from __future__ import annotations

from typing import List, Tuple

Pixel = Tuple[int, int, int]


class SoftwareCanvas:
    """In-memory implementation of the FrameCanvas methods used by the app."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.pixels: List[List[Pixel]] = []
        self.Clear()

    def Clear(self) -> None:
        self.pixels = [
            [(0, 0, 0) for _ in range(self.width)]
            for _ in range(self.height)
        ]

    def Fill(self, red: int, green: int, blue: int) -> None:
        color = (red, green, blue)
        self.pixels = [
            [color for _ in range(self.width)]
            for _ in range(self.height)
        ]

    def SetPixel(
        self, x: int, y: int, red: int, green: int, blue: int
    ) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y][x] = (red, green, blue)


class SoftwareMatrix:
    """Drop-in matrix for tests and hardware-free development."""

    def __init__(self, width: int = 128, height: int = 64):
        self.width = width
        self.height = height
        self.canvas = SoftwareCanvas(width, height)

    def CreateFrameCanvas(self) -> SoftwareCanvas:
        return self.canvas

    def SwapOnVSync(self, canvas: SoftwareCanvas) -> SoftwareCanvas:
        self.canvas = canvas
        return canvas

    def Clear(self) -> None:
        self.canvas.Clear()


def create_hardware_matrix():
    """Create the Raspberry Pi matrix, importing its binding on demand."""
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    except ImportError as exc:
        raise RuntimeError(
            "The hardware matrix backend requires the rpi-rgb-led-matrix "
            "Python binding. Build it on the Raspberry Pi, or run with "
            "--software on other machines."
        ) from exc

    options = RGBMatrixOptions()
    options.rows = 64
    options.cols = 64
    options.chain_length = 2
    options.parallel = 1
    options.hardware_mapping = "regular"
    options.gpio_slowdown = 4
    options.brightness = 80
    options.disable_hardware_pulsing = True

    print(
        f"[matrix] rows={options.rows} cols={options.cols} "
        f"chain={options.chain_length} parallel={options.parallel} "
        f"mapping={options.hardware_mapping!r} "
        f"slowdown={options.gpio_slowdown} brightness={options.brightness}"
    )
    return RGBMatrix(options=options)


def create_matrix(*, software: bool = False):
    if software:
        print("[matrix] using 128x64 in-memory software backend")
        return SoftwareMatrix()
    return create_hardware_matrix()

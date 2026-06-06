import builtins

import pytest

from core import PanelView
from matrix_backend import SoftwareMatrix, create_hardware_matrix, create_matrix


def test_software_matrix_supports_runtime_canvas_interface():
    matrix = create_matrix(software=True)
    canvas = matrix.CreateFrameCanvas()
    view = PanelView(canvas, 64)

    view.set_pixel(2, 3, 10, 20, 30)
    swapped = matrix.SwapOnVSync(canvas)

    assert swapped is canvas
    assert matrix.width == 128
    assert matrix.height == 64
    assert canvas.pixels[3][66] == (10, 20, 30)

    matrix.Clear()
    assert canvas.pixels[3][66] == (0, 0, 0)


def test_hardware_dependency_is_loaded_only_for_hardware_backend(monkeypatch):
    original_import = builtins.__import__

    def without_rgbmatrix(name, *args, **kwargs):
        if name == "rgbmatrix":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_rgbmatrix)

    with pytest.raises(RuntimeError, match="--software"):
        create_hardware_matrix()

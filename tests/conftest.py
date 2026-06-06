"""
conftest.py — shared fixtures and hardware stubs.

Both rgbmatrix and rplidar are only available on Raspberry Pi hardware.
This file stubs them into sys.modules before any project code is imported,
so tests can run on any machine.
"""

import sys
from unittest.mock import MagicMock

import pytest


# ── Hardware stubs ───────────────────────────────────────────────────────────────
# Must be in place before the first import of streams or main.

for _mod in ("rgbmatrix", "rplidar"):
    sys.modules.setdefault(_mod, MagicMock())


# ── Test reporting ────────────────────────────────────────────────────────────────

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"report_{report.when}", report)


@pytest.fixture(autouse=True)
def trace_test(request):
    """Give every HTML report row a minimal execution trace."""
    test_id = request.node.nodeid
    print(f"[test] START {test_id}")
    yield
    report = getattr(request.node, "report_call", None)
    result = report.outcome.upper() if report is not None else "UNKNOWN"
    print(f"[test] {result} {test_id}")
    print(f"[test] END {test_id}")


@pytest.fixture
def step():
    """Record numbered, human-readable test steps in captured output."""
    count = 0

    def record(message):
        nonlocal count
        count += 1
        print(f"[step {count}] {message}")

    return record


# ── Shared fixtures ───────────────────────────────────────────────────────────────

class SpyCanvas:
    """
    Minimal stand-in for an rgbmatrix FrameCanvas.

    Records every SetPixel call so tests can assert on what was drawn
    without touching real hardware.
    """

    def __init__(self):
        self.pixels: dict[tuple, tuple] = {}   # (x, y) → (r, g, b)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int):
        self.pixels[(x, y)] = (r, g, b)

    def get(self, x: int, y: int) -> tuple:
        return self.pixels.get((x, y), (0, 0, 0))

    def any_lit(self) -> bool:
        return any(c != (0, 0, 0) for c in self.pixels.values())


@pytest.fixture
def spy_canvas():
    return SpyCanvas()


@pytest.fixture
def mock_matrix(spy_canvas):
    """
    Mock rgbmatrix.RGBMatrix that returns a SpyCanvas from CreateFrameCanvas()
    and records SwapOnVSync calls.

    SwapOnVSync raises KeyboardInterrupt on its second call so Runtime.run()
    exits after exactly one rendered frame.
    """
    m = MagicMock()
    m.CreateFrameCanvas.return_value = spy_canvas

    call_count = {"n": 0}

    def _swap(canvas):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise KeyboardInterrupt
        return canvas

    m.SwapOnVSync.side_effect = _swap
    return m

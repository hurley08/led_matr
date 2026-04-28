#!/usr/bin/env python3
"""
visualize.py — preview both panels as a PNG. No hardware needed.

Uses the exact same RadarMap and Dashboard classes that run on hardware,
rendered into a mock canvas and scaled up 8× with a LED glow effect.
What you see here is pixel-for-pixel what the matrix will show.

    pip install pillow
    python3 visualize.py                  # saves led_preview.png
    python3 visualize.py --animate        # saves led_preview_00–19.png
"""

import math
import os
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from streams import build_streams
from panels.map_panel import RadarMap
from panels.dashboard import Dashboard

PANEL_W = PANEL_H = 64
SCALE   = 8


# ── Mock LED canvas ──────────────────────────────────────────────────────────────
# Implements the same SetPixel interface that rgbmatrix.FrameCanvas exposes,
# so PanelView works without any changes.

class MockCanvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self._p = [[(0, 0, 0)] * w for _ in range(h)]

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int):
        if 0 <= x < self.w and 0 <= y < self.h:
            self._p[y][x] = (r, g, b)

    def to_image(self) -> Image.Image:
        img  = Image.new("RGB", (self.w * SCALE, self.h * SCALE), (4, 4, 4))
        draw = ImageDraw.Draw(img)
        for y in range(self.h):
            for x in range(self.w):
                r, g, b = self._p[y][x]
                px, py  = x * SCALE, y * SCALE
                draw.rectangle([px, py, px + SCALE - 1, py + SCALE - 1],
                                fill=(10, 10, 10))
                if r | g | b:
                    draw.ellipse([px, py, px + SCALE - 1, py + SCALE - 1],
                                 fill=(r // 5, g // 5, b // 5))
                    m = max(1, SCALE // 4)
                    draw.ellipse([px + m, py + m,
                                  px + SCALE - 1 - m, py + SCALE - 1 - m],
                                 fill=(r, g, b))
        return img


# ── Composite frame ───────────────────────────────────────────────────────────────

BORDER  = 16
TITLE_H = 36
FOOT_H  = 28

def _pil_font(size: int) -> ImageFont.ImageFont:
    for path in [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def compose(led_img: Image.Image) -> Image.Image:
    lw, lh   = led_img.size
    total_w  = lw + BORDER * 2
    total_h  = lh + BORDER * 2 + TITLE_H + FOOT_H
    out      = Image.new("RGB", (total_w, total_h), (14, 14, 14))
    draw     = ImageDraw.Draw(out)

    draw.rectangle([0, 0, total_w, TITLE_H - 1], fill=(22, 22, 22))
    tf   = _pil_font(12)
    p1cx = BORDER + (PANEL_W * SCALE) // 2
    p2cx = BORDER + PANEL_W * SCALE + (PANEL_W * SCALE) // 2
    draw.text((p1cx, TITLE_H // 2),
              "PANEL 1 — MAP / COORDINATE SYSTEM (64×64)",
              fill=(180, 180, 180), font=tf, anchor="mm")
    draw.text((p2cx, TITLE_H // 2),
              "PANEL 2 — HEURISTIC DASHBOARD (64×64)",
              fill=(180, 180, 180), font=tf, anchor="mm")

    div_x = BORDER + PANEL_W * SCALE
    draw.line([(div_x, 0), (div_x, TITLE_H + lh)], fill=(55, 55, 55), width=2)
    out.paste(led_img, (BORDER, TITLE_H))

    sf = _pil_font(9)
    leg_y = TITLE_H + (PANEL_H - 3) * SCALE - 11
    draw.text((BORDER + 2,               leg_y), "CLOSE",
              fill=(255, 80, 80),  font=sf)
    draw.text((BORDER + PANEL_W*SCALE//2, leg_y), "DISTANCE",
              fill=(180, 180, 180), font=sf, anchor="mt")
    draw.text((BORDER + PANEL_W*SCALE-2,  leg_y), "FAR",
              fill=(120, 80, 220), font=sf, anchor="rt")

    draw.rectangle([0, TITLE_H + lh + BORDER - BORDER, total_w, total_h],
                   fill=(18, 18, 18))
    draw.text((total_w // 2, total_h - FOOT_H // 2),
              "BOTH PANELS: 64×64 RGB LED MATRIX  |  8× SCALE PREVIEW",
              fill=(110, 110, 110), font=sf, anchor="mm")
    draw.rectangle([0, 0, total_w - 1, total_h - 1], outline=(40, 40, 40), width=1)
    return out


# ── Render one frame ─────────────────────────────────────────────────────────────

def render_frame(t: float = 0.0) -> Image.Image:
    from core import Panel, PanelView

    scan_s, sector_s = build_streams(mock=True)
    # Advance mock time by calling update repeatedly
    for _ in range(int(t * 7)):
        scan_s.update()
    scan_s.update()
    sector_s.update()

    canvas = MockCanvas(PANEL_W * 2, PANEL_H)

    map_viz  = RadarMap(heading_deg=15.0)
    dash_viz = Dashboard()

    map_view  = PanelView(canvas, Panel.LEFT.value)
    dash_view = PanelView(canvas, Panel.RIGHT.value)

    map_view.clear()
    dash_view.clear()

    map_viz.render(map_view,  lidar_scan=scan_s.latest)
    dash_viz.render(dash_view, lidar_sectors=sector_s.latest)

    return compose(canvas.to_image())


# ── Entry point ──────────────────────────────────────────────────────────────────

def main():
    animate = "--animate" in sys.argv
    if animate:
        for i in range(20):
            img  = render_frame(t=i / 20 * 2 * math.pi)
            name = f"led_preview_{i:02d}.png"
            img.save(name)
            print(f"  saved {name}")
        print("Done — 20 frames written.")
    else:
        img  = render_frame(t=4.0)   # t≈4 → front obstacle close → DANGER
        path = "led_preview.png"
        img.save(path)
        print(f"Saved {path}  ({img.width}×{img.height} px)")
        try:
            import subprocess
            subprocess.Popen(["open", path])
        except Exception:
            pass

if __name__ == "__main__":
    main()

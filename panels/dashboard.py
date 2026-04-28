"""
panels/dashboard.py — heuristic dashboard visualization.

Subscribes to: lidar.sectors
Panel:         RIGHT

Row layout (64 rows total)
──────────────────────────
  0– 9   Danger status bar  (coloured fill + text)
 10       blank
 11–18   Sector labels: LT / FT / RT
 19–30   Sector proximity bars
 31       separator
 32–39   DNS label + value
 40–41   Density bar
 42–49   AVG label + value
 50–51   Avg-dist bar
 52–59   MIN label + value
 60–61   Min-dist bar
 62–63   Health strip (colour only)
"""

from __future__ import annotations

from core import Panel, PanelView, Visualization
from streams import SectorStats

W = H = 64

DANGER_MM  = 500
CAUTION_MM = 1000
MAX_DIST   = 3000

# Sector column x-ranges (local coords within the 64-wide panel)
_SECTOR_COLS = [(0, 19), (22, 41), (44, 63)]


# ── Colour helpers ───────────────────────────────────────────────────────────────

def _danger_color(mm: float) -> tuple:
    if mm < DANGER_MM:  return (255,  40,  40)
    if mm < CAUTION_MM: return (255, 200,   0)
    return (0, 210, 60)


# ── Pixel font rendering ─────────────────────────────────────────────────────────
# We pre-render text into tiny PIL images and stamp them into the PanelView.
# This keeps font logic isolated and matches the 5×8 BDF font used on hardware.

from PIL import Image, ImageDraw, ImageFont as _PILFont

def _load_font(path: str | None = None):
    if path:
        try:
            return _PILFont.truetype(path, 8)
        except Exception:
            pass
    try:
        return _PILFont.load_default(size=8)
    except TypeError:
        return _PILFont.load_default()

_FONT = _load_font()

def _text_width(text: str) -> int:
    bb = _FONT.getbbox(text)
    return bb[2] - bb[0]

def _draw_text(view: PanelView, x: int, y: int,
               text: str, r: int, g: int, b: int):
    bb  = _FONT.getbbox(text)
    tw  = bb[2] - bb[0]
    th  = bb[3] - bb[1]
    tmp = Image.new("L", (tw + 2, th + 2), 0)
    ImageDraw.Draw(tmp).text((1 - bb[0], 1 - bb[1]), text, fill=255, font=_FONT)
    for py in range(tmp.height):
        for px in range(tmp.width):
            if tmp.getpixel((px, py)) > 64:
                view.set_pixel(x + px, y + py, r, g, b)


# ── Sub-renderers ────────────────────────────────────────────────────────────────

def _sector_col(view: PanelView, col_idx: int, dist_mm: float):
    x0, x1  = _SECTOR_COLS[col_idx]
    bar_w   = x1 - x0 + 1
    r, g, b = _danger_color(dist_mm)

    view.fill_rect(x0, 19, x1, 30, 16, 16, 16)

    fill_w = max(1, int(min(dist_mm, MAX_DIST) / MAX_DIST * bar_w))
    for y in range(19, 31):
        for x in range(x0, x0 + fill_w):
            factor = 0.55 + 0.45 * (x - x0) / max(1, fill_w - 1)
            view.set_pixel(x, y,
                           int(r * factor),
                           int(g * factor),
                           int(b * factor))

def _horiz_bar(view: PanelView, y0: int, y1: int,
               value_0_1: float, r: int, g: int, b: int):
    fill_w = max(1, int(value_0_1 * W))
    view.fill_rect(0, y0, W - 1, y1, 16, 16, 16)
    view.fill_rect(0, y0, fill_w - 1, y1, r, g, b)


# ── Visualization ────────────────────────────────────────────────────────────────

class Dashboard(Visualization):
    """
    Heuristic dashboard showing obstacle proximity and scan quality.

    Danger bar   Full-width coloured bar + text (DANGER / CAUTION / CLEAR).
    Sectors      LT / FT / RT proximity bars (fuller = farther = safer).
    Metrics      DNS density, AVG average distance, MIN minimum distance,
                 HEALTH scan quality — each as a labelled bar.

    Subscribes to: lidar.sectors
    """

    panel   = Panel.RIGHT
    streams = ["lidar.sectors"]

    def __init__(self, font_path: str | None = None):
        """
        Parameters
        ──────────
        font_path   Optional path to a .bdf or .ttf font file.
                    If omitted, uses PIL's built-in 8px bitmap font.
        """
        global _FONT
        _FONT = _load_font(font_path)

    def render(self, view: PanelView, *, lidar_sectors: SectorStats, **_):
        s = lidar_sectors
        dr, dg, db = _danger_color(s.min_dist)

        # ── Danger bar ──────────────────────────────────────────────────────
        view.fill_rect(0, 0, W - 1, 9, dr, dg, db)
        if s.min_dist < DANGER_MM:
            label, tr, tg, tb = "!! DANGER !!", 255, 255, 255
        elif s.min_dist < CAUTION_MM:
            label, tr, tg, tb = "CAUTION",       20,  20,  20
        else:
            label, tr, tg, tb = "CLEAR",         20,  20,  20
        lw = _text_width(label)
        _draw_text(view, (W - lw) // 2, 1, label, tr, tg, tb)

        # ── Sector labels ───────────────────────────────────────────────────
        for tag, dist_mm, (x0, x1) in [
            ("LT", s.left,  _SECTOR_COLS[0]),
            ("FT", s.front, _SECTOR_COLS[1]),
            ("RT", s.right, _SECTOR_COLS[2]),
        ]:
            mid = (x0 + x1) // 2
            _draw_text(view, mid - _text_width(tag) // 2, 11, tag, 0, 200, 230)

        # ── Sector bars ─────────────────────────────────────────────────────
        _sector_col(view, 0, s.left)
        _sector_col(view, 1, s.front)
        _sector_col(view, 2, s.right)

        # ── Separator ───────────────────────────────────────────────────────
        view.fill_rect(0, 31, W - 1, 31, 40, 40, 40)

        # ── Metric rows ─────────────────────────────────────────────────────
        metrics = [
            ("DNS", f"{s.density:.0f}%",      32, 40, 41,   0, 200,  60,
             s.density / 100.0),
            ("AVG", f"{s.avg_dist/1000:.1f}m", 42, 50, 51,  30, 150, 255,
             min(s.avg_dist / MAX_DIST, 1.0)),
            ("MIN", f"{s.min_dist/1000:.2f}m", 52, 60, 61, 220,   0, 220,
             min(s.min_dist / MAX_DIST, 1.0)),
        ]
        for tag, val, lrow, by0, by1, r, g, b, norm in metrics:
            _draw_text(view, 1,                        lrow, tag, r, g, b)
            _draw_text(view, W - _text_width(val) - 1, lrow, val, r, g, b)
            _horiz_bar(view, by0, by1, norm, r, g, b)

        # ── Health strip (colour mirrors danger state) ───────────────────────
        _horiz_bar(view, 62, 63, s.health / 100.0, dr, dg, db)

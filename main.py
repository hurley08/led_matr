#!/usr/bin/env python3
"""
matrix_init.py
Two chained 64x64 HUB75 LED matrices on Raspberry Pi 4
Using hzeller's rpi-rgb-led-matrix library

--- Setup (run these on the RPi4 first) ---

1. Install dependencies:
      sudo apt-get update && sudo apt-get install -y python3-dev python3-pillow

2. Clone and build the library:
      git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
      cd rpi-rgb-led-matrix
      make build-python PYTHON=$(which python3)
      sudo make install-python PYTHON=$(which python3)

3. Disable onboard audio (it conflicts with the PWM the library uses):
      Edit /boot/config.txt (or /boot/firmware/config.txt on newer RPi OS)
      Change:  dtparam=audio=on
      To:      dtparam=audio=off
      Then reboot.

4. Wiring — no HAT, direct GPIO (BCM numbering):
      Use the "regular" hardware mapping from the hzeller wiring guide:
      https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md

      Key connections (verify against the guide above):
        R1 → GPIO 5    G1 → GPIO 13   B1 → GPIO 6
        R2 → GPIO 12   G2 → GPIO 16   B2 → GPIO 23
        A  → GPIO 22   B  → GPIO 26   C  → GPIO 27
        D  → GPIO 20   E  → GPIO 24   (E needed for 64 rows)
        OE → GPIO 18   CLK → GPIO 17  LAT → GPIO 4

      ⚠️  Power the panels from a dedicated 5V/4A+ supply.
          Share GND between the supply and the RPi4.

5. Run with sudo (required for GPIO access):
      sudo python3 matrix_init.py
"""

import sys
import os
import time
import math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

# ---------------------------------------------------------------------------
# Matrix configuration
# ---------------------------------------------------------------------------

def create_matrix() -> RGBMatrix:
    options = RGBMatrixOptions()

    options.rows            = 64          # height of one panel
    options.cols            = 64          # width of one panel
    options.chain_length    = 2           # two panels daisy-chained
    options.parallel        = 1           # single chain
    options.hardware_mapping = "regular"  # no HAT — direct GPIO wiring
    options.gpio_slowdown   = 4           # RPi4 is fast; slowdown prevents glitches
    options.brightness      = 80          # 0–100; lower = less heat & power draw
    options.disable_hardware_pulsing = True
    return RGBMatrix(options=options)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def fill(canvas, r: int, g: int, b: int):
    """Fill the entire canvas with one colour."""
    canvas.Fill(r, g, b)


def draw_border(canvas, x: int, y: int, w: int, h: int, r: int, g: int, b: int):
    """Draw a 1-pixel border rectangle."""
    for px in range(x, x + w):
        canvas.SetPixel(px, y,         r, g, b)
        canvas.SetPixel(px, y + h - 1, r, g, b)
    for py in range(y, y + h):
        canvas.SetPixel(x,         py, r, g, b)
        canvas.SetPixel(x + w - 1, py, r, g, b)


# ---------------------------------------------------------------------------
# Startup test
# ---------------------------------------------------------------------------

PANEL_W = 64
PANEL_H = 64

def panel_jump_test(matrix: RGBMatrix, canvas):
    """Animate a moving square jumping between the two panels for visual inspection."""
    square_size = 10
    speed = 8 # pixels per frame
    delay = 0.05  # seconds between frames
    
    # Start from left edge
    x = 0
    y = PANEL_H // 2 - square_size // 2  # Center vertically
    
    while x < 128  - square_size:
        canvas.Clear()
        # Draw the square
        for px in range(x, x + square_size):
            for py in range(y, y + square_size):
                canvas.SetPixel(px, py, 255, 255, 255)  # White square
        
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(delay)
        x += speed

    # Bounce back to the left
    while x > 0:
        canvas.Clear()
        for px in range(x, x + square_size):
            for py in range(y, y + square_size):
                canvas.SetPixel(px, py, 255, 255, 255)
        
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(delay)
        x -= speed


def panel_diag_jump_test(matrix: RGBMatrix, radius: int, canvas):
    """Animate a circle jumping diagonally between the two panels."""
    speed = 8  # pixels per frame
    delay = 0.05  # seconds between frames

    # Start from top-left corner of left panel
    x = 0
    y = 0

    while x < 128 - radius * 2 and y < PANEL_H - radius * 2:
        canvas.Clear()
        # Draw the circle using distance check
        for px in range(x, x + radius * 2):
            for py in range(y, y + radius * 2):
                # Check if point is within circle
                dx = px - (x + radius)
                dy = py - (y + radius)
                if dx*dx + dy*dy <= radius*radius:
                    # Ensure pixel is within canvas bounds
                    if 0 <= px < 128 and 0 <= py < PANEL_H:
                        canvas.SetPixel(px, py, 255, 255, 255)

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(delay)
        x += speed
        y += speed

    # Bounce back diagonally
    while x > 0 and y > 0:
        canvas.Clear()
        # Ensure we don't draw outside canvas bounds
        start_x = max(0, x)
        start_y = max(0, y)
        end_x = min(128, x + radius * 2)
        end_y = min(PANEL_H, y + radius * 2)

        for px in range(start_x, end_x):
            for py in range(start_y, end_y):
                # Check if point is within circle bounds
                dx = px - (x + radius)
                dy = py - (y + radius)
                if dx*dx + dy*dy <= radius*radius:
                    canvas.SetPixel(px, py, 255, 255, 255)

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(delay)
        x -= speed
        y -= speed

    return canvas

def startup_test(matrix: RGBMatrix):
    canvas = matrix.CreateFrameCanvas()
    # Smooth sector danger to prevent one bad scan from dropping a bar to zero.
    sector_danger_smoothed = {
        "front": 0.0,
        "right": 0.0,
        "back": 0.0,
        "left": 0.0,
    }

    # Create array of [r, g, b] where each swings from 0-255 using sine waves
    num_steps = 256
    colors = []
    for i in range(num_steps):
        r = int(255 * (math.sin(i * 2 * math.pi / num_steps) + 1) / 2)
        g = int(255 * (math.sin(i * 2 * math.pi / num_steps + 2 * math.pi / 3) + 1) / 2)
        b = int(255 * (math.sin(i * 2 * math.pi / num_steps + 4 * math.pi / 3) + 1) / 2)
        colors.append((r, g, b))

    # Flash through the swinging colors
    for color in colors:
        fill(canvas, *color)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.01)  # Adjust speed as needed

    # Draw red border on left panel, blue border on right panel
    canvas.Clear()
    draw_border(canvas, 0,       0, PANEL_W, PANEL_H, 255, 0,   0)
    draw_border(canvas, PANEL_W, 0, PANEL_W, PANEL_H, 0,   0, 255)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(1.5)

    canvas.Clear()
    canvas = matrix.SwapOnVSync(canvas)
    panel_jump_test(matrix, canvas)
    return canvas



def render_two_moving_objects(matrix: RGBMatrix, canvas):
    """Animate two objects moving independently on the panels, bouncing off edges."""
    speed_1 = 8  # pixels per frame
    speed_2 = 4  # pixels per frame  
    delay = 0.05  # seconds between frames
    frames_to_render = 500

    # Object 1 starts on left panel, moves right
    x1 = 0
    y1 = PANEL_H // 3
    dx1 = speed_1  # direction for x1

    # Object 2 starts on right panel, moves left
    x2 = matrix.width - 10
    y2 = PANEL_H * 2 // 3
    dx2 = -speed_2  # direction for x2

    while frames_to_render > 0:
        canvas.Clear()
        # Draw object 1 (white square)
        for px in range(x1, x1 + 10):
            for py in range(y1, y1 + 10):
                canvas.SetPixel(px, py, 255, 255, 255)

        # Draw object 2 (cyan square)
        for px in range(x2, x2 + 10):
            for py in range(y2, y2 + 10):
                canvas.SetPixel(px, py, 0, 255, 255)

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(delay)
        
        # Move object 1
        x1 += dx1
        if x1 < 0:
            x1 = 0
            dx1 = -dx1
        elif x1 + 10 > matrix.width:
            x1 = matrix.width - 10
            dx1 = -dx1
        
        # Move object 2
        x2 += dx2
        if x2 < 0:
            x2 = 0
            dx2 = -dx2
        elif x2 + 10 > matrix.width:
            x2 = matrix.width - 10
            dx2 = -dx2
        
        frames_to_render -= 1


def led_sequence_test(matrix: RGBMatrix, canvas):
    """Turn on and off each LED in sequence."""
    delay = 0.00001 # seconds between each LED change
    canvas.Clear()
    
    # Turn on each LED in sequence
    for y in range(matrix.height):
        for x in range(matrix.width):
            canvas.SetPixel(x, y, 50, 255, 50)  
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(delay)
    
    time.sleep(0.5)  # Pause before turning off
    
    # Turn off each LED in sequence
    for y in range(matrix.height):
        for x in range(matrix.width):
            canvas.SetPixel(x, y, 255, 50, 255)  # Black
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(delay)
    
    return canvas


# ---------------------------------------------------------------------------
# RPLidar radar renderer
# ---------------------------------------------------------------------------

def lidar_radar(matrix: RGBMatrix, port: str = '/dev/ttyUSB0', max_distance: int = 3000):
    """
    Render RPLidar A1 readings as a live top-down radar on the LED matrix.

    Coordinate convention:
        angle=0° → top of display (forward), increasing clockwise.
        Orient the sensor so its 0° faces the same direction as the top of the panels.
    """
    # Import locally so this still works when running as sudo/root.
    from rplidar_a1 import RPLidarA1

    def clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def draw_hbar(canvas, x: int, y: int, w: int, value: float, r: int, g: int, b: int):
        value = clamp(value, 0.0, 1.0)
        fill_w = int(w * value)
        for px in range(x, x + w):
            # Dim baseline
            canvas.SetPixel(px, y, 20, 20, 20)
        for px in range(x, x + fill_w):
            canvas.SetPixel(px, y, r, g, b)

    def try_load_label_font():
        font = graphics.Font()
        candidates = [
            "/home/pi4/Projects/rpi-rgb-led-matrix/fonts/tom-thumb.bdf",
            "/home/pi4/Projects/rpi-rgb-led-matrix/fonts/4x6.bdf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    font.LoadFont(path)
                    return font
                except Exception:
                    pass
        return None

    CANVAS_H = matrix.height  # 64

    # Two-panel layout: left 64x64 panel = radar map, right 64x64 panel = heuristics.
    MAP_X0 = 0
    MAP_W = 64
    HEUR_X0 = 64
    HEUR_W = 64
    DANGER_CLOSE_MM = 300
    DIR_BAR_BASE_Y = 58
    DIR_BAR_TOP_Y = 33
    RADAR_ZOOM_GAMMA = 0.6
    RADAR_PLOT_RATIO = 0.55      # omit map points beyond this fraction of max_distance
    SECTOR_HOLD_FRAMES = 14
    SECTOR_HOLD_TRIGGER = 0.35

    CX = MAP_X0 + (MAP_W // 2)  # center map on left panel
    CY = CANVAS_H // 2
    MAX_R = min(MAP_W // 2, CANVAS_H // 2) - 2
    label_font = try_load_label_font()
    label_color = graphics.Color(180, 180, 180)

    canvas = matrix.CreateFrameCanvas()
    sector_danger_smoothed = {
        "front": 0.0,
        "right": 0.0,
        "back": 0.0,
        "left": 0.0,
    }
    sector_danger_hold = {
        "front": 0,
        "right": 0,
        "back": 0,
        "left": 0,
    }

    print(f"Lidar radar running on {port}. Press Ctrl+C to stop.")
    try:
        with RPLidarA1(port) as lidar:
            for scan in lidar.iter_scans():
                canvas.Clear()

                nearest = float(max_distance)
                dist_sum = 0.0
                count = 0
                valid_distances = []
                sector_distances = {
                    "front": [],
                    "right": [],
                    "back": [],
                    "left": [],
                }

                # Panel separators / guides
                draw_border(canvas, MAP_X0, 0, MAP_W, CANVAS_H, 40, 40, 40)
                draw_border(canvas, HEUR_X0, 0, HEUR_W, CANVAS_H, 40, 40, 40)

                # Yellow dot at sensor origin
                canvas.SetPixel(CX, CY, 255, 255, 0)

                for (quality, angle, distance) in scan:
                    if distance <= 0:
                        continue

                    d = min(distance, max_distance)
                    ratio = d / max_distance
                    r_px = int((ratio ** RADAR_ZOOM_GAMMA) * MAX_R)
                    a = angle % 360.0
                    rad = math.radians(angle)
                    # Rotate radar map 90 degrees clockwise.
                    px = int(CX + r_px * math.cos(rad))
                    py = int(CY + r_px * math.sin(rad))

                    nearest = min(nearest, d)
                    dist_sum += d
                    count += 1
                    valid_distances.append(d)

                    # Sector assignment uses raw lidar angle (not map-rotation offset).
                    if a >= 315.0 or a < 45.0:
                        sector_distances["front"].append(d)
                    elif a < 135.0:
                        sector_distances["right"].append(d)
                    elif a < 225.0:
                        sector_distances["back"].append(d)
                    else:
                        sector_distances["left"].append(d)

                    if MAP_X0 <= px < (MAP_X0 + MAP_W) and 0 <= py < CANVAS_H:
                        # Points within DANGER_CLOSE_MM: pure red.
                        # Beyond that, grade red -> yellow up to RADAR_PLOT_RATIO cutoff.
                        if ratio <= RADAR_PLOT_RATIO:
                            danger_ratio = DANGER_CLOSE_MM / max_distance
                            if ratio <= danger_ratio:
                                canvas.SetPixel(px, py, 255, 0, 0)
                            else:
                                plot_t = (ratio - danger_ratio) / (RADAR_PLOT_RATIO - danger_ratio)
                                canvas.SetPixel(px, py, 255, int(255 * plot_t), 0)

                if count > 0:
                    avg = dist_sum / count
                else:
                    avg = float(max_distance)
                    nearest = float(max_distance)

                # Use a low-percentile distance instead of raw min so one noisy
                # close sample does not pin the safety indicator red.
                if valid_distances:
                    ordered = sorted(valid_distances)
                    idx = int(0.1 * (len(ordered) - 1))
                    danger_distance = ordered[idx]
                else:
                    danger_distance = float(max_distance)

                danger_close = danger_distance <= DANGER_CLOSE_MM

                # Heuristics panel (right):
                # 1) nearest obstacle (red), 2) average range (blue), 3) sample density (white)
                # 4) directional clearance bars F/R/B/L (green when clear, red when blocked)
                # Distance-normalized nearest reading (0=very close, 1=far).
                n_ratio = clamp(nearest / max_distance, 0.0, 1.0)
                # Proximity score uses robust danger distance so noise doesn't pin
                # the metric high when nothing is truly danger-close.
                n_prox = clamp((DANGER_CLOSE_MM - danger_distance) / DANGER_CLOSE_MM, 0.0, 1.0)
                a_ratio = clamp(avg / max_distance, 0.0, 1.0)
                c_ratio = clamp(count / 240.0, 0.0, 1.0)

                # Keep distance semantics consistent with map colors:
                # red = near/danger, green = far/clear.
                n_r = int(255 * n_prox)
                n_g = int(255 * (1.0 - n_prox))
                a_r = int(255 * (1.0 - a_ratio))
                a_g = int(255 * a_ratio)

                draw_hbar(canvas, HEUR_X0 + 4, 6, 56, n_prox, n_r, n_g, 0)
                draw_hbar(canvas, HEUR_X0 + 4, 12, 56, a_ratio, a_r, a_g, 0)
                draw_hbar(canvas, HEUR_X0 + 4, 18, 56, c_ratio, 220, 220, 220)

                # --- Update per-sector smoothed danger values ---
                directions = ["front", "right", "back", "left"]
                for direction in directions:
                    values = sector_distances[direction]
                    if values:
                        values_sorted = sorted(values)
                        idx = int(0.1 * (len(values_sorted) - 1))
                        p10 = values_sorted[idx]
                        danger_raw = clamp((DANGER_CLOSE_MM - p10) / DANGER_CLOSE_MM, 0.0, 1.0)
                        if danger_raw >= SECTOR_HOLD_TRIGGER:
                            sector_danger_hold[direction] = SECTOR_HOLD_FRAMES
                        prev = sector_danger_smoothed[direction]
                        alpha = 0.55 if danger_raw > prev else 0.18
                        sector_danger_smoothed[direction] = (alpha * danger_raw) + ((1.0 - alpha) * prev)
                    else:
                        prev = sector_danger_smoothed[direction]
                        if sector_danger_hold[direction] > 0:
                            sector_danger_hold[direction] -= 1
                            sector_danger_smoothed[direction] = prev * 0.995
                        else:
                            sector_danger_smoothed[direction] = prev * 0.95

                # Unify danger_close: trigger if global p10 OR any sector is danger-close.
                danger_close = danger_close or any(
                    sector_danger_smoothed[d] >= SECTOR_HOLD_TRIGGER for d in directions
                )

                # Safety status section: color drives both strip and FRBL bars.
                status_r = 220 if danger_close else 0
                status_g = 0 if danger_close else 220
                for py in range(24, 32):
                    for px in range(HEUR_X0 + 4, HEUR_X0 + 60):
                        canvas.SetPixel(px, py, status_r, status_g, 0)

                if label_font is not None:
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 1, 8, label_color, "N")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 1, 14, label_color, "A")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 1, 20, label_color, "D")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 6, 31, graphics.Color(0, 0, 0), "SAFE" if not danger_close else "DANG")

                # FRBL bars: height = per-sector danger level, color matches SAFE/DANG flag.
                for i, direction in enumerate(directions):
                    danger = sector_danger_smoothed[direction]
                    x = HEUR_X0 + 4 + i * 14
                    max_h = DIR_BAR_BASE_Y - DIR_BAR_TOP_Y + 1
                    h = int(max_h * danger)
                    for py in range(DIR_BAR_BASE_Y, DIR_BAR_BASE_Y - h, -1):
                        if py < DIR_BAR_TOP_Y:
                            break
                        canvas.SetPixel(x, py, status_r, status_g, 0)
                        canvas.SetPixel(x + 1, py, status_r, status_g, 0)
                        canvas.SetPixel(x + 2, py, status_r, status_g, 0)

                if label_font is not None:
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 5, 63, label_color, "F")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 19, 63, label_color, "R")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 33, 63, label_color, "B")
                    graphics.DrawText(canvas, label_font, HEUR_X0 + 47, 63, label_color, "L")

                canvas = matrix.SwapOnVSync(canvas)

    except KeyboardInterrupt:
        pass
    finally:
        canvas.Clear()
        matrix.SwapOnVSync(canvas)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import sys
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'

    matrix = create_matrix()
    startup_test(matrix)
    lidar_radar(matrix, port=port)
    matrix.Clear()
    print("Done.")


if __name__ == "__main__":
    main()


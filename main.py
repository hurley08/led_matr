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

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import time
import math

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

def startup_test(matrix: RGBMatrix):
    canvas = matrix.CreateFrameCanvas()    # Flash through basic colours
    for colour in [(255,0,0), (0,255,0), (0,0,255), (255,255,255), (0,0,0)]:
        fill(canvas, *colour)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(1.5)

    # Draw red border on left panel, blue border on right panel
    canvas.Clear()
    draw_border(canvas, 0,       0, PANEL_W, PANEL_H, 255, 0,   0)
    draw_border(canvas, PANEL_W, 0, PANEL_W, PANEL_H, 0,   0, 255)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(1.5)

    canvas.Clear()
    canvas = matrix.SwapOnVSync(canvas)
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
    from rplidar_a1 import RPLidarA1

    CANVAS_W = matrix.width   # 128
    CANVAS_H = matrix.height  # 64
    CX = CANVAS_W // 2        # 64 — horizontal center
    CY = CANVAS_H // 2        # 32 — vertical center
    MAX_R = CY - 2            # 30 px — radius fits panel height

    canvas = matrix.CreateFrameCanvas()

    print(f"Lidar radar running on {port}. Press Ctrl+C to stop.")
    try:
        with RPLidarA1(port) as lidar:
            for scan in lidar.iter_scans():
                canvas.Clear()

                # Yellow dot at sensor origin
                canvas.SetPixel(CX, CY, 255, 255, 0)

                for (quality, angle, distance) in scan:
                    d = min(distance, max_distance)
                    ratio = d / max_distance
                    r_px = int(ratio * MAX_R)

                    rad = math.radians(angle)
                    px = int(CX + r_px * math.sin(rad))
                    py = int(CY - r_px * math.cos(rad))

                    if 0 <= px < CANVAS_W and 0 <= py < CANVAS_H:
                        # Green (close) → red (far)
                        canvas.SetPixel(px, py, int(255 * ratio), int(255 * (1 - ratio)), 0)

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


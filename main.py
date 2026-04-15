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
    """Animate two objects moving independently on the panels."""
    speed_1= 8 # pixels per frame
    speed_2= 4 # pixels per frame  
    delay = 0.05  # seconds between frames

    # Object 1 starts on left panel, moves right
    x1 = 0
    y1 = PANEL_H // 3

    # Object 2 starts on right panel, moves left
    x2 = PANEL_W * 2 - 10
    y2 = PANEL_H * 2 // 3

    while x1 < PANEL_W * 2 - 10 and x2 > PANEL_W:
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
        x1 += speed
        x2 -= speed


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
# Main
# ---------------------------------------------------------------------------
def main():
    font = graphics.Font()
    font.LoadFont("/home/pi4/projects/led_matr/rpi-rgb-led-matrix/fonts/5x8.bdf")

    matrix = create_matrix()
    canvas = startup_test(matrix)
    canvas = render_two_moving_objects(matrix, canvas)
    canvas = startup_test_old(matrix)
    canvas = panel_diag_jump_test(matrix, 10, canvas)
    canvas = led_sequence_test(matrix, canvas)

    
    graphics.DrawText(canvas, font, 10, 36, graphics.Color(0, 255, 0), "P1")
    graphics.DrawText(canvas, font, PANEL_W + 10, 36, graphics.Color(255, 255, 0), "P2")
    canvas = matrix.SwapOnVSync(canvas)
    print(f"Matrix ready: {matrix.width}x{matrix.height} "
          f"({matrix.width // PANEL_W} panel(s) chained)")

    print("Startup complete. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        matrix.Clear()
        print("Cleared.")


if __name__ == "__main__":
    main()


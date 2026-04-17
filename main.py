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
from lidar_controller import UsbLidarController
import time
import math
import random

# ---------------------------------------------------------------------------
# Matrix configuration
# ---------------------------------------------------------------------------

def create_matrix() -> RGBMatrix:
    options = RGBMatrixOptions()

    options.rows            = 64          # height of one panel
    options.cols            = 64          # width of one panel
    options.chain_length    = 3           # two panels daisy-chained
    options.parallel        = 1           # single chain
    options.hardware_mapping = "regular"  # no HAT — direct GPIO wiring
    options.gpio_slowdown   = 4           # RPi4 is fast; slowdown prevents glitches
    options.brightness      = 40          # 0–100; lower = less heat & power draw
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


def draw_all_panel_borders(canvas, matrix: RGBMatrix, panel_w: int, panel_h: int):
    """Draw a border around each panel-sized tile across the full matrix."""
    colours = [
        (255, 0, 0),
        (0, 0, 255),
        (0, 200, 0),
        (255, 180, 0),
        (255, 0, 255),
        (0, 255, 255),
    ]
    tiles_x = max(1, (matrix.width + panel_w - 1) // panel_w)
    tiles_y = max(1, (matrix.height + panel_h - 1) // panel_h)

    index = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            x = tx * panel_w
            y = ty * panel_h
            w = min(panel_w, matrix.width - x)
            h = min(panel_h, matrix.height - y)
            if w <= 0 or h <= 0:
                continue
            r, g, b = colours[index % len(colours)]
            draw_border(canvas, x, y, w, h, r, g, b)
            index += 1


def draw_random_shape(canvas, x: int, y: int, w: int, h: int):
    """Draw one random shape inside the given region."""
    if w < 3 or h < 3:
        return

    r = random.randint(50, 255)
    g = random.randint(50, 255)
    b = random.randint(50, 255)
    shape = random.choice(["rect", "circle", "line"])

    if shape == "rect":
        draw_border(canvas, x, y, w, h, r, g, b)
        for px in range(x + 1, x + w - 1):
            for py in range(y + 1, y + h - 1):
                canvas.SetPixel(px, py, r, g, b)
    elif shape == "circle":
        radius = min(w, h) // 2 - 1
        cx = x + w // 2
        cy = y + h // 2
        for px in range(x, x + w):
            for py in range(y, y + h):
                dx = px - cx
                dy = py - cy
                if dx * dx + dy * dy <= radius * radius:
                    canvas.SetPixel(px, py, r, g, b)
        draw_border(canvas, x, y, w, h, r, g, b)
    else:
        for i in range(min(w, h)):
            if x + i < x + w and y + i < y + h:
                canvas.SetPixel(x + i, y + i, r, g, b)
            if x + i < x + w and y + h - 1 - i >= y:
                canvas.SetPixel(x + i, y + h - 1 - i, r, g, b)


def split_and_draw_random_shapes(canvas, x: int, y: int, w: int, h: int, min_size: int = 8):
    """Split the viewing area into quadrants and draw random shapes recursively."""
    if w < min_size or h < min_size:
        return

    draw_random_shape(canvas, x, y, w, h)

    half_w = w // 2
    half_h = h // 2

    split_and_draw_random_shapes(canvas, x, y, half_w, half_h, min_size)
    split_and_draw_random_shapes(canvas, x + half_w, y, w - half_w, half_h, min_size)
    split_and_draw_random_shapes(canvas, x, y + half_h, half_w, h - half_h, min_size)
    split_and_draw_random_shapes(canvas, x + half_w, y + half_h, w - half_w, h - half_h, min_size)


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

    # Draw borders for all panel tiles.
    canvas.Clear()
    draw_all_panel_borders(canvas, matrix, PANEL_W, PANEL_H)
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

    # Draw borders for all panel tiles.
    canvas.Clear()
    draw_all_panel_borders(canvas, matrix, PANEL_W, PANEL_H)
    canvas = matrix.SwapOnVSync(canvas)
    time.sleep(1.5)

    canvas.Clear()
    canvas = matrix.SwapOnVSync(canvas)
    return canvas

def render_two_moving_objects(matrix: RGBMatrix, canvas, font):
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
        print(f"Frames left: {frames_to_render}", end="\r")
    
        graphics.DrawText(canvas, font, 10, 36, graphics.Color(0, 255, 0), "Frames left")
        graphics.DrawText(canvas, font, PANEL_W + 10, 36, graphics.Color(255, 255, 0), str(frames_to_render))
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



def led_sequence_test(matrix: RGBMatrix, canvas, font, cycles: int = 1):
    """Turn each LED on/off in sequence and show a per-cycle remaining counter."""
    delay = 0.00001  # seconds between each LED change
    total_pixels = matrix.width * matrix.height
    cycle_count = max(1, cycles)
    counter_x = PANEL_W + 10
    counter_y = 36
    # 5 glyphs @ 5px width + spacing, with vertical room for 5x8 font.
    counter_w = 32
    counter_h = 10

    def clear_counter_box():
        for py in range(counter_y - 8, counter_y - 8 + counter_h):
            for px in range(counter_x, counter_x + counter_w):
                if 0 <= px < matrix.width and 0 <= py < matrix.height:
                    canvas.SetPixel(px, py, 0, 0, 0)

    graphics.DrawText(canvas, font, 10, 36, graphics.Color(0, 255, 0), "px left")

    for _ in range(cycle_count):
        left_to_do = total_pixels
        for y in range(matrix.height):
            for x in range(matrix.width):
                canvas.SetPixel(x, y, 50, 255, 50)
                # Fixed-width counter avoids artifacts without clearing the whole panel.
                clear_counter_box()
                graphics.DrawText(
                    canvas,
                    font,
                    counter_x,
                    counter_y,
                    graphics.Color(255, 255, 0),
                    f"{left_to_do:05d}",
                )
                canvas = matrix.SwapOnVSync(canvas)
                try:
                    canvas.SetPixel(x-5, y, 125, 0, 125)
                except:
                    pass  # Ignore out-of-bounds for the first few pixels
                left_to_do -= 1
                time.sleep(delay)


        time.sleep(0.5)

    # Ensure no counter glyphs remain after the final OFF cycle.
    clear_counter_box()
    canvas = matrix.SwapOnVSync(canvas)

    return canvas


def display_lidar_readings(matrix: RGBMatrix, canvas, font, lidar: UsbLidarController):
    """Render live LiDAR readings on both panels until interrupted."""
    no_data_seconds = 0.0
    warned_no_data = False
    while True:
        measurement = lidar.get_latest_measurement()

        if measurement:
            no_data_seconds = 0.0
            warned_no_data = False
        else:
            no_data_seconds += 0.05
            if no_data_seconds >= 5.0 and not warned_no_data:
                print(
                    "LiDAR connected but no parsed samples after 5s. "
                    "If this is an RPLidar, enable startup commands and verify model protocol."
                )
                warned_no_data = True

        canvas.Clear()
        draw_all_panel_borders(canvas, matrix, PANEL_W, PANEL_H)

        graphics.DrawText(canvas, font, 2, 10, graphics.Color(255, 255, 255), "LIDAR")
        graphics.DrawText(canvas, font, PANEL_W + 2, 10, graphics.Color(255, 255, 255), "READING")

        if measurement:
            left_lines = [
                f"A:{measurement.angle_deg:5.1f}",
                f"D:{measurement.distance_mm:5.0f}",
                f"Q:{measurement.quality if measurement.quality is not None else '--'}",
            ]
            right_lines = [
                f"ANG {measurement.angle_deg:5.1f}",
                f"DST {measurement.distance_mm:5.0f}",
                f"TS {int(measurement.timestamp) % 10000:04d}",
            ]

            for i, text in enumerate(left_lines):
                graphics.DrawText(canvas, font, 2, 22 + i * 10, graphics.Color(0, 255, 0), text)
            for i, text in enumerate(right_lines):
                graphics.DrawText(
                    canvas,
                    font,
                    PANEL_W + 2,
                    22 + i * 10,
                    graphics.Color(255, 255, 0),
                    text,
                )
        else:
            graphics.DrawText(canvas, font, 2, 28, graphics.Color(255, 180, 0), "WAITING")
            graphics.DrawText(canvas, font, 2, 38, graphics.Color(255, 180, 0), "FOR DATA")
            graphics.DrawText(canvas, font, PANEL_W + 2, 28, graphics.Color(255, 180, 0), "CHECK")
            graphics.DrawText(canvas, font, PANEL_W + 2, 38, graphics.Color(255, 180, 0), "USB/BAUD")

        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    font = graphics.Font()
    font.LoadFont("/home/pi4/projects/led_matr/rpi-rgb-led-matrix/fonts/5x8.bdf")
    # CP210x/RPLidar style sensors typically need startup control frames.
    lidar = UsbLidarController(baudrate=115200, use_rplidar_startup=True, use_rplidar_driver=True)
    matrix = create_matrix()
    canvas = startup_test(matrix)



    print(f"Matrix ready: {matrix.width}x{matrix.height} "
          f"({matrix.width // PANEL_W} panel(s) chained)")

    print("Startup complete. Press Ctrl+C to exit.")

    try:
        lidar_port = lidar.connect()
        lidar.start()
        print(
            f"LiDAR connected on {lidar_port} @ {lidar.baudrate} baud "
            f"(mode={lidar.driver_mode})"
        )
    except RuntimeError as exc:
        print(f"LiDAR unavailable: {exc}")
        
    try:
        display_lidar_readings(matrix, canvas, font, lidar)
    except KeyboardInterrupt:
        lidar.disconnect()
        matrix.Clear()
        print("Cleared.")


    canvas = render_two_moving_objects(matrix, canvas, font)
    canvas = startup_test(matrix)
    canvas = panel_diag_jump_test(matrix, 10, canvas)
    canvas = led_sequence_test(matrix, canvas, font)
    
    graphics.DrawText(canvas, font, 10, 36, graphics.Color(0, 255, 0), "P1")
    graphics.DrawText(canvas, font, PANEL_W + 10, 36, graphics.Color(255, 255, 0), "P2")
    canvas = matrix.SwapOnVSync(canvas)


if __name__ == "__main__":
    main()


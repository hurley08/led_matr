# LED Matrix Display

A Python application for controlling two chained 64x64 HUB75 LED matrices on a Raspberry Pi 4 using the hzeller rpi-rgb-led-matrix library.

## Features

- **Dual Panel Display**: Controls two 64x64 LED panels (128x64 total resolution)
- **Startup Diagnostics**: Includes various test patterns and animations
- **Panel Jump Test**: Animates a square moving horizontally across both panels
- **Diagonal Circle Test**: Animates a circle moving diagonally across both panels
- **Color Cycling**: Displays rainbow color transitions during startup
- **USB LiDAR Controller**: Reusable class for reading LiDAR samples via `/dev/ttyUSB*` or `/dev/ttyACM*`
- **Live LiDAR Overlay**: Shows angle, distance, quality, and timestamp data on both LED panels

## Hardware Requirements

- Raspberry Pi 4
- Two 64x64 HUB75 LED matrices
- 5V/4A+ dedicated power supply for the LED panels
- GPIO connections (see wiring section below)

## Software Setup

### 1. Install Dependencies

```bash
sudo apt-get update && sudo apt-get install -y python3-dev python3-pillow
pip3 install pyserial
```

### 2. Clone and Build the LED Matrix Library

```bash
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python PYTHON=$(which python3)
sudo make install-python PYTHON=$(which python3)
```

### 3. Disable Onboard Audio

Edit `/boot/config.txt` (or `/boot/firmware/config.txt` on newer RPi OS):

```bash
# Change this line:
dtparam=audio=on
# To:
dtparam=audio=off
```

Then reboot: `sudo reboot`

## Wiring

Uses direct GPIO wiring (no HAT required). Follow the "regular" hardware mapping from the [hzeller wiring guide](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md).

### Key GPIO Connections (BCM numbering):
- R1 → GPIO 5
- G1 → GPIO 13
- B1 → GPIO 6
- R2 → GPIO 12
- G2 → GPIO 16
- B2 → GPIO 23
- A → GPIO 22
- B → GPIO 26
- C → GPIO 27
- D → GPIO 20
- E → GPIO 24  (required for 64 rows)
- OE → GPIO 18
- CLK → GPIO 17
- LAT → GPIO 4

⚠️ **Important**: Power the LED panels from a dedicated 5V/4A+ supply. Share GND between the power supply and the Raspberry Pi.

## Usage

Run with sudo (required for GPIO access):

```bash
sudo python3 main.py
```

### LiDAR Class Usage

The project includes `UsbLidarController` in `lidar_controller.py`.

```python
from lidar_controller import UsbLidarController
import time

lidar = UsbLidarController(baudrate=230400)
lidar.start()

try:
	while True:
		m = lidar.get_latest_measurement()
		if m:
			print(f"angle={m.angle_deg:.1f} distance={m.distance_mm:.1f}mm quality={m.quality}")
		time.sleep(0.1)
finally:
	lidar.disconnect()
```

If your LiDAR uses a specific serial port, pass it explicitly:

```python
lidar = UsbLidarController(port="/dev/ttyUSB0", baudrate=230400)
```

Supported incoming LiDAR line formats:
- `angle,distance`
- `angle,distance,quality`
- `angle:12.5 distance:840 q:180`

The application will:
1. Initialize the LED matrix
2. Run startup diagnostic tests (color cycling, border drawing)
3. Display panel labels ("P1" and "P2")
4. Run the panel jump test animation
5. Run the diagonal circle test animation
6. Connect to LiDAR over USB serial (auto-detects `/dev/ttyUSB*` and `/dev/ttyACM*`)
7. Continuously display live LiDAR readings on both panels until Ctrl+C

## Configuration

Matrix settings can be adjusted in the `create_matrix()` function:
- `rows`: Height of one panel (64)
- `cols`: Width of one panel (64)
- `chain_length`: Number of panels chained (2)
- `brightness`: LED brightness (0-100, default 80)
- `gpio_slowdown`: GPIO timing adjustment (4 for RPi4)

## Troubleshooting

- **No display**: Check power supply, wiring connections, and GPIO pin assignments
- **Flickering**: Increase `gpio_slowdown` value or check for electrical interference
- **Permission errors**: Must run with `sudo` for GPIO access
- **Audio conflicts**: Ensure onboard audio is disabled in `/boot/config.txt`
- **No LiDAR data**: Verify port with `ls /dev/ttyUSB* /dev/ttyACM*`, confirm baudrate, and check USB power/cable
- **LiDAR not found**: Pass `port="/dev/ttyUSB0"` (or the detected port) when creating `UsbLidarController`

## License

This project uses the [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library.

# led_matr

Real-time RPLIDAR visualizer on two chained 64×64 HUB75 LED panels driven by a Raspberry Pi 4.

## Panels

| Panel | Content |
|-------|---------|
| LEFT  | Radar map — 360° point cloud plotted in polar coordinates |
| RIGHT | Dashboard — danger bar, sector proximity bars, scan metrics |

## Dashboard layout

```
 0– 9   Danger bar — UNDEF / CLEAR / CAUTION / !! DANGER !! (all-angle min distance)
10–18   Sector labels: LT / FT / RT
19–30   Sector proximity bars (full = close, red; empty = clear, green)
31      Separator
32–41   DNS density label + bar
42–51   AVG average distance label + bar
52–61   MIN minimum distance label + bar
62–63   Health strip
```

Danger thresholds (configurable in `panels/dashboard.py`):
- `DANGER_MM = 150` — red, `!! DANGER !!`
- `CAUTION_MM = 1500` — yellow, `CAUTION`
- `≥ CAUTION_MM` — green, `CLEAR`
- No valid readings — black, `UNDEF`

## Hardware

- Raspberry Pi 4
- Two 64×64 HUB75 LED matrices chained (128×64 total)
- SLAMTEC RPLIDAR A1M8
- 5V/4A+ dedicated supply for LED panels
- CP2102 or CH340 USB-serial adapter for RPLIDAR

## Software setup

### 1. Install dependencies

```bash
sudo apt-get update && sudo apt-get install -y python3-dev python3-pillow python3-serial
python3 -m pip install -e ".[rpi]"
```

For development or CI without Raspberry Pi hardware:

```bash
python3 -m pip install -e ".[dev]"
```

`requirements.txt` and `requirements-ci.txt` are retained temporarily for
existing environments while dependency management migrates to
`pyproject.toml`.

### 2. Build and install the LED matrix library

The `rpi-rgb-led-matrix` Python binding is not published on PyPI, so it is
built separately rather than listed in the `rpi` dependency extra.

```bash
cd rpi-rgb-led-matrix
make build-python PYTHON=$(which python3)
sudo make install-python PYTHON=$(which python3)
```

### 3. Disable onboard audio (required for GPIO DMA)

In `/boot/config.txt` (or `/boot/firmware/config.txt`):
```
dtparam=audio=off
```
Then reboot.

## Usage

```bash
sudo python3 main.py                        # real RPLIDAR on /dev/ttyUSB0
sudo python3 main.py --port=/dev/ttyUSB1    # specify port
sudo python3 main.py --mock                 # mock data, no hardware needed
     python3 main.py --list                 # list streams and exit
```

Boot output includes `[boot]`, `[lidar]`, `[matrix]`, and `[runtime]` prefixed diagnostics at each stage.

## Matrix configuration

Settings in `main.py` `create_matrix()`:

| Option | Value |
|--------|-------|
| rows | 64 |
| cols | 64 |
| chain_length | 2 |
| brightness | 80 |
| gpio_slowdown | 4 (RPi4) |
| hardware_mapping | regular |
| disable_hardware_pulsing | True |

## RPLIDAR driver (`rplidar.py`)

Custom minimal driver (replaces unmaintained PyPI `rplidar` package):
- Speaks the SLAMTEC serial protocol directly over pyserial
- Motor control via DTR line (active-low: `dtr=False` = motor on)
- Issues `CMD_RESET` on connect to guarantee a clean idle state before scanning
- Actively drains the serial buffer after reset to discard boot output
- `iter_scans()` yields full 360° revolutions as `(quality, angle_deg, distance_mm)` lists

## Sector definitions

Lidar mounted 180° from forward — sectors are rotated accordingly:

| Sector | Angle range |
|--------|------------|
| Front  | 135°–225°  |
| Left   | 225°–315°  |
| Right  | 45°–135°   |

## Wiring (regular mapping)

See [hzeller wiring guide](https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md) for GPIO pin assignments. Power LED panels from a dedicated 5V/4A+ supply with shared GND to the Pi.

## Troubleshooting

| Symptom | Cause / fix |
|---------|------------|
| Motor stops on connect | DTR polarity — `dtr=False` must be set immediately after `open()` |
| `descriptor short: 0 bytes` | Sensor not yet idle — `CMD_RESET` + drain resolves this |
| `bad descriptor sync` | Stale scan bytes in buffer — active drain clears them |
| Ctrl-C ignored | Per-point print flood — never print inside `iter_scans` hot path |
| Dashboard stuck on UNDEF | No valid points — check scan health and distance filter bounds |

- **Permission errors**: Must run with `sudo` for GPIO access
- **Audio conflicts**: Ensure onboard audio is disabled in `/boot/config.txt`

## License

This project uses the [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library.

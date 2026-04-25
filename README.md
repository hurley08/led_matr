# LED Matrix + RPLidar Radar Display

Python app for two chained 64x64 HUB75 panels on Raspberry Pi 4, using hzeller rpi-rgb-led-matrix and a SLAMTEC RPLidar A1.

## What It Does

- Runs startup diagnostics on a 128x64 display.
- Uses a split layout during lidar mode:
	- Left panel (64x64): radar map centered on the panel.
	- Right panel (64x64): heuristic metrics and safety indicators.

## Current Lidar UI Layout

ASCII panel map (128x64 total):

```text
+------------------------------+------------------------------+
|          LEFT PANEL          |         RIGHT PANEL          |
|            (64x64)           |            (64x64)           |
|                              | N  [nearest danger score]    |
|      Radar points + origin   | A  [average distance]        |
|      red=danger, yellow=far  | D  [scan density]            |
|                              | [ SAFE / DANG status strip ] |
|                              | F  R  B  L bars              |
+------------------------------+------------------------------+
```

Left panel:
- Radar map with sensor origin at center (yellow dot).
- Map is rotated 90° CW; forward faces the top of the display.
- Non-linear zoom (gamma 0.6) for better near-field detail.
- Point color semantics:
	- Pure red = within DANGER_CLOSE_MM (danger zone)
	- Orange → yellow = beyond danger zone up to ~55% of max range
	- Nothing plotted beyond 55% of max_distance (deep-far points omitted)

Right panel (heuristics):
- N bar: nearest-proximity danger score. Red when close, green when far.
- A bar: average distance across all returns. Red when close, green when far.
- D bar: sample density (white intensity).
- SAFE/DANG status strip:
	- Green (SAFE) when no obstacle is within DANGER_CLOSE_MM and no sector is triggered.
	- Red (DANG) when the global p10 distance or any individual sector exceeds the threshold.
- FRBL bars (Front, Right, Back, Left):
	- Height reflects per-sector danger level (smoothed with hysteresis).
	- Color matches the SAFE/DANG flag — green when safe, red when danger.
	- Sectors use raw lidar angle (0° = forward, increasing clockwise).

Label support:
- Uses a tiny BDF font when available to draw N, A, D, SAFE/DANG, and F/R/B/L labels.
- Font probe order:
	1. /home/pi4/Projects/rpi-rgb-led-matrix/fonts/tom-thumb.bdf
	2. /home/pi4/Projects/rpi-rgb-led-matrix/fonts/4x6.bdf

## Hardware

- Raspberry Pi 4
- Two 64x64 HUB75 LED panels
- RPLidar A1 (USB serial)
- Dedicated 5V / 4A or better panel power supply

Important:
- Share ground between panel PSU and Pi.
- Use direct GPIO regular mapping (no HAT).

## Wiring (BCM)

- R1 -> GPIO 5
- G1 -> GPIO 13
- B1 -> GPIO 6
- R2 -> GPIO 12
- G2 -> GPIO 16
- B2 -> GPIO 23
- A -> GPIO 22
- B -> GPIO 26
- C -> GPIO 27
- D -> GPIO 20
- E -> GPIO 24 (needed for 64-row panels)
- OE -> GPIO 18
- CLK -> GPIO 17
- LAT -> GPIO 4

Reference:
- https://github.com/hzeller/rpi-rgb-led-matrix/blob/master/wiring.md

## Setup

1. Install OS packages

	 sudo apt-get update
	 sudo apt-get install -y python3-dev python3-pillow

2. Install Python serial dependency

	 pip3 install pyserial

3. Build and install matrix bindings

	 git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
	 cd rpi-rgb-led-matrix
	 make build-python PYTHON=$(which python3)
	 sudo make install-python PYTHON=$(which python3)

4. Disable onboard audio PWM conflict

	 Edit /boot/config.txt (or /boot/firmware/config.txt)
	 Change:
	 dtparam=audio=on
	 To:
	 dtparam=audio=off

	 Reboot after editing.

## Run

From this folder:

	 cd /home/pi4/Projects/led_matr
	 python3 main.py /dev/ttyUSB0

If your lidar appears on a different serial device, pass that path instead.

## Permission Notes

- Lidar serial access needs dialout group membership.
- Matrix timing quality is best with elevated scheduling rights.
- You may still see non-root timing warnings from the matrix library even when capabilities are configured.

Useful checks:

	 groups
	 ls -l /dev/ttyUSB0

## Tunable Constants (in main.py)

Inside `lidar_radar()`:
- `max_distance` (default 3000 mm): radar scaling distance cap.
- `DANGER_CLOSE_MM` (default 300 mm): SAFE→DANG threshold. Also sets the red/yellow boundary on the map — pure red dots on the map are danger-close.
- `RADAR_PLOT_RATIO` (default 0.55): fraction of max_distance beyond which map points are omitted. Points between DANGER_CLOSE_MM and this cutoff grade orange→yellow.
- `RADAR_ZOOM_GAMMA` (default 0.6): nonlinear zoom exponent for near-field detail.
- `SECTOR_HOLD_FRAMES` / `SECTOR_HOLD_TRIGGER`: hysteresis for FRBL bars (hold frames and trigger threshold).

Matrix options in `create_matrix()`:
- `rows`, `cols`, `chain_length`, `parallel`
- `hardware_mapping`
- `gpio_slowdown`
- `brightness`
- `disable_hardware_pulsing`

## Startup Sequence

1. Matrix init
2. Color sweep
3. Panel border test
4. Horizontal jump test
5. Live lidar radar + heuristics until Ctrl+C

## Troubleshooting

- No panel output:
	- Check panel power and shared ground.
	- Verify GPIO wiring and regular hardware mapping.
- Color shimmer or flicker:
	- Increase `gpio_slowdown` in `create_matrix()`.
- Lidar read failures or intermittent serial exceptions:
	- Re-seat USB cable.
	- Verify stable lidar power.
	- Confirm no other process is using /dev/ttyUSB0.
- SAFE/DANG seems too sensitive or never triggers:
	- The RPLidar A1 has a hardware blind zone of ~150 mm minimum range.
	- Setting `DANGER_CLOSE_MM` below ~150 mm means the lidar physically cannot report readings in that zone, so the threshold will never trigger.
	- Keep `DANGER_CLOSE_MM` above 150 mm for reliable detection.
	- Increase `DANGER_CLOSE_MM` for earlier warning; decrease for stricter (closer) warning.
- Map points not visible at expected distances:
	- Points beyond `RADAR_PLOT_RATIO * max_distance` are intentionally omitted.
	- Increase `RADAR_PLOT_RATIO` (up to 1.0) to show farther points.

## License

Uses hzeller rpi-rgb-led-matrix:
- https://github.com/hzeller/rpi-rgb-led-matrix

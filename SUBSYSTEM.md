# LED Matrix Display Subsystem

A pub/sub framework for driving the two 64×64 LED panels.
Data **streams** feed into **visualizations** through a **runtime** —
adding a new display layout means writing one file and registering it in `main.py`.

---

## Concepts

### Stream
A named, self-describing data source. Streams are either **primary** (pull from
a sensor or external source) or **derived** (transform another stream's output).

```python
Stream(
    name        = "lidar.scan",
    description = "Raw point cloud — List[Point(angle, distance, quality)]",
    source      = scanner.get_scan,         # called every frame
)
```

Derived streams declare what they depend on:

```python
Stream(
    name       = "lidar.sectors",
    description = "...",
    source     = lambda: analyze(lidar_scan.latest),
    depends_on = ["lidar.scan"],            # updated after primaries
)
```

### Visualization
Subscribes to one or more streams by name and renders into a 64×64 panel view.
Subclass `Visualization`, set `panel` and `streams`, implement `render()`.

```python
from core import Panel, PanelView, Visualization

class MyDisplay(Visualization):
    panel   = Panel.RIGHT          # Panel.LEFT or Panel.RIGHT
    streams = ["lidar.sectors"]    # stream names to subscribe to

    def render(self, view: PanelView, *, lidar_sectors, **_):
        # view is a 64×64 local coordinate space — (0,0) is always top-left
        view.fill_rect(0, 0, 63, 7, *danger_color(lidar_sectors.min_dist))
        view.set_pixel(32, 32, 255, 255, 255)
```

Stream names are passed as keyword arguments with dots replaced by underscores
(`lidar.sectors` → `lidar_sectors`). Use `**_` to silently ignore extras.

### PanelView
A 64×64 window into the full matrix canvas. Handles the x-offset for you so
visualization code never needs to know which physical panel it is on.

| Method | Description |
|--------|-------------|
| `set_pixel(x, y, r, g, b)` | Set one LED |
| `fill(r, g, b)` | Fill the entire panel |
| `fill_rect(x0, y0, x1, y1, r, g, b)` | Fill a rectangle |
| `clear()` | Black out the panel |

### Runtime
Connects streams to visualizations and drives the render loop.

```python
rt = (
    Runtime()
    .add_stream(scan_stream)
    .add_stream(sector_stream)
    .add_visualization(RadarMap())
    .add_visualization(MyDisplay())
)

rt.list_streams()   # print all streams + active visualizations
rt.run(matrix)      # blocks; Ctrl-C exits cleanly
```

---

## Available streams

| Name | Type | Description |
|------|------|-------------|
| `lidar.scan` | `List[Point]` | Raw point cloud — `Point(angle, distance, quality)` |
| `lidar.sectors` | `SectorStats` | Per-sector analysis — see fields below |

**SectorStats fields**

| Field | Unit | Description |
|-------|------|-------------|
| `front` | mm | Minimum distance, front sector (315°–45°) |
| `left` | mm | Minimum distance, left sector (225°–315°) |
| `right` | mm | Minimum distance, right sector (45°–135°) |
| `min_dist` | mm | Global minimum across all points |
| `avg_dist` | mm | Global average distance |
| `density` | 0–100 | Percentage of angular bins with a valid return |
| `health` | 0–100 | Scan quality estimate |

---

## Built-in visualizations

| Class | Panel | Streams | Description |
|-------|-------|---------|-------------|
| `RadarMap` | LEFT | `lidar.scan` | Colour-coded top-down radar map |
| `Dashboard` | RIGHT | `lidar.sectors` | Danger bar, sector proximity bars, metric readouts |

---

## Adding a new visualization

1. Create a file in `panels/`.
2. Subclass `Visualization`, declare `panel` and `streams`, implement `render()`.
3. Register it in `main.py`.

```python
# panels/compass.py
from core import Panel, PanelView, Visualization

class Compass(Visualization):
    panel   = Panel.LEFT
    streams = ["lidar.scan"]

    def render(self, view: PanelView, *, lidar_scan, **_):
        ...
```

```python
# main.py
from panels.compass import Compass
rt.add_visualization(Compass())
```

## Adding a new stream

Add the stream definition to `streams.py` and call `rt.add_stream()` in `main.py`.
Derived streams receive another stream's `.latest` value via a lambda.

```python
# streams.py
heading_stream = Stream(
    name        = "imu.heading",
    description = "Robot heading in degrees from IMU",
    source      = imu.get_heading,
)
```

---

## Running

```bash
# Hardware
sudo python3 main.py

# Mock data (no RPLidar needed)
python3 main.py --mock

# List streams and exit
python3 main.py --list

# PNG preview at 8× scale (no hardware needed)
python3 visualize.py

# Animated preview (20 frames)
python3 visualize.py --animate
```

---

## File map

```
core.py              Stream, Visualization, PanelView, Runtime
streams.py           Stream definitions + data types (Point, SectorStats)
panels/
  map_panel.py       RadarMap visualization
  dashboard.py       Dashboard visualization
visualize.py         PNG preview — uses the real panel classes, no rgbmatrix needed
main.py              Wires everything together
```

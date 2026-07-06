# morton — Morton Code Spatial Sorting

> Auto-generated code target: `core/morton.py`

## 1. Purpose

Morton (Z-order) curve encoding for 3D points. Used to sort splats spatially for better compression in SPX/SPZ/GLB writers.

## 2. Data Structures

### 2.1 V3MinMax

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| min_x, min_y, min_z | float | 0.0 | Axis minimums |
| max_x, max_y, max_z | float | 0.0 | Axis maximums |
| len_x, len_y, len_z | float | 0.0 | Axis spans (max - min) |
| center_x, center_y, center_z | float | 0.0 | Axis midpoints |
| radius | float | 0.0 | Bounding sphere radius |

## 3. Public API

### 3.1 `compute_xyz_min_max(data: SplatData) -> V3MinMax`
- **Description**: Compute axis-aligned bounds, spans, center, and bounding sphere radius from positions.
- **Algorithm**: `np.min/max` on each position axis.
- **Edge Cases**: Empty data → all zeros.

### 3.2 `compute_xyz_log_min_max(data: SplatData) -> V3MinMax`
- **Description**: Same as above but applies `sog_encode_log` to positions first. Used by SOG writer.
- **Algorithm**: Loop through positions, apply `sog_encode_log`, compute min/max/spans from log values.

### 3.3 `encode_morton3(positions: np.ndarray, mm: V3MinMax) -> np.ndarray`
- **Description**: Encode N×3 positions to N uint32 Morton codes.
- **Algorithm**:
  1. Normalize each axis to [0, 1023] using `mm` bounds
  2. Spread bits: `part1_by2(z) << 2 | part1_by2(y) << 1 | part1_by2(x)`
  3. `part1_by2` expands 10-bit integer: `x = (x ^ (x << 16)) & 0xFF0000FF`, etc.
- **Edge Cases**: Axis length = 0 → use 1023 to avoid NaN. Values outside bounds → clamped.

### 3.4 `sort_morton(data: SplatData) -> None`
- **Description**: Sort all SplatData arrays by Morton code (in-place).
- **Algorithm**: `compute_xyz_min_max` → `encode_morton3` → `np.argsort` → reorder all arrays.

## 4. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Empty data (count=0) | All functions return early or return zeros |
| Axis span = 0 | Morton encode uses 1023 for all values on that axis |
| Positions outside [min, max] | Clipped to [0, 1023] range |

## 5. Examples

```python
from pygsbox.core.morton import V3MinMax, encode_morton3, sort_morton
import numpy as np

data = SplatData(20)
data.position = np.random.randn(20, 3).astype(np.float32)
sort_morton(data)  # in-place spatial sort
```

## 6. Dependencies

| Module | Used for |
|--------|----------|
| numpy | ndarray operations |

## 7. Agent Notes

- **Morton bit spread**: `part1_by2` is a classic bit-manipulation pattern. Use uint32 arithmetic.
- **sort_morton reorders ALL SplatData arrays**: position, scale, color, rotation, sh, is_watermark, flag_value, palette_idx, lod.
- **Vectorized**: `encode_morton3` operates on all points at once via numpy broadcasting.

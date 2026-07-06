# splat_data — Core Data Structure

> Auto-generated code target: `core/splat_data.py`

## 1. Purpose

`SplatData` is the universal interchange format for all 3DGS data in pygsbox.  
Every format reader produces it; every format writer consumes it.  
Uses **NumPy columnar arrays** for performance (not a list of per-splat objects).

## 2. Data Structures

### 2.1 SplatData

| Attribute | Dtype | Shape | Default (N=0) | Purpose |
|-----------|-------|-------|---------------|---------|
| `count` | int | scalar | 0 | Number of splats |
| `position` | float32 | (N, 3) | `zeros((0,3))` | XYZ world-space center |
| `scale` | float32 | (N, 3) | `zeros((0,3))` | Log-space scale (exp to get world) |
| `color` | uint8 | (N, 4) | `zeros((0,4))` | RGBA (A=opacity, uint8 encoded) |
| `rotation` | uint8 | (N, 4) | `zeros((0,4))` | Quaternion (W, X, Y, Z order), uint8 encoded |
| `sh` | uint8 | (N, 45) | `zeros((0,45))` | SH coefficients (up to degree 3 = 15 bands × 3 channels) |
| `is_watermark` | bool | (N,) | `zeros(0)` | True if this splat is a watermark |
| `flag_value` | uint16 | (N,) | `zeros(0)` | Reserved flag field |
| `palette_idx` | uint16 | (N,) | `zeros(0)` | K-Means SH palette index |
| `lod` | uint16 | (N,) | `zeros(0)` | LOD level tag |

### 2.2 Splat Format Layout (32 bytes)

Used by `.splat` files. Each splat is exactly 32 bytes:

| Offset | Size | Type | Content |
|--------|------|------|---------|
| 0 | 12 | float32×3 | Position (X, Y, Z) |
| 12 | 12 | float32×3 | Scale (already decoded from log-space) |
| 24 | 4 | uint8×4 | Color (R, G, B, A) |
| 28 | 4 | uint8×4 | Rotation (W, X, Y, Z) |

## 3. Public API

### 3.1 Constructor

#### `__init__(self, count: int = 0) -> None`
- **Description**: Create a SplatData with `count` splats or empty.
- **Side Effects**: Allocates numpy arrays.

### 3.2 Methods

#### `append(self, other: 'SplatData') -> None`
- **Description**: Concatenate another SplatData's arrays to this one.
- **Edge Cases**: If self is empty (count=0), just copy other's arrays. If other is empty, no-op.

#### `filter_alpha(self, min_alpha: int) -> 'SplatData'`
- **Description**: Return a new SplatData containing only splats where `color[:, 3] >= min_alpha`.
- **Edge Cases**: If min_alpha <= 0, return self unchanged.

#### `subset(self, mask: np.ndarray) -> 'SplatData'`
- **Description**: Create a new SplatData from a boolean mask.
- **Preconditions**: `mask` must be 1D bool array of length `self.count`.

#### `compute_bounds(self) -> Tuple[np.ndarray, np.ndarray]`
- **Description**: Compute (min_pos, max_pos) from position array.
- **Edge Cases**: If count=0, return `(zeros(3), zeros(3))`.

#### `compute_center_radius(self) -> Tuple[np.ndarray, float]`
- **Description**: Compute bounding sphere center and radius from position array.
- **Edge Cases**: If count=0, return `(zeros(3), 0.0)`.

### 3.3 Free Functions

#### `from_splat_format_bytes(data: bytes, count: int) -> 'SplatData'`
- **Description**: Decode 32-byte/splat raw bytes into SplatData.
- **Preconditions**: `len(data) == count * 32`.

#### `to_splat_format_bytes(splat: 'SplatData') -> bytes`
- **Description**: Encode SplatData to 32-byte/splat raw bytes.
- **Postconditions**: `len(result) == splat.count * 32`.

## 4. Algorithm

### 4.1 Splat Format Encode

```
For each of 8 float32 fields (pos×3, scale×3, 2 pad):
    Copy 4 bytes from SplatData arrays
For each of 8 uint8 fields (color×4, rotation×4):
    Copy 1 byte from SplatData arrays
```

Implementation uses `np.frombuffer` for performance.

### 4.2 Splat Format Decode

```
1. View raw bytes as uint8 array of shape (count, 32)
2. Extract position (columns 0-11) as float32 via frombuffer
3. Extract scale (columns 12-23) as float32 via frombuffer
4. Extract color (columns 24-27) as uint8
5. Extract rotation (columns 28-31) as uint8
```

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `SplatData(0)` | All arrays shape (0, ...) |
| `append(empty)` | No-op |
| `append to empty` | Copies other's arrays |
| `filter_alpha(0)` | Returns self unchanged |
| `filter_alpha(256)` | Returns empty SplatData |
| `subset(mask_zeros(False))` | Empty SplatData |
| `to_splat_format_bytes(empty)` | Returns `b''` |
| `from_splat_format_bytes(b'', 0)` | Returns empty SplatData |
| 32-byte block not divisible by 32 | `read_splat()` raises `ValueError` |

## 6. Examples

### 6.1 Create and Modify

```python
from pygsbox.core.splat_data import SplatData
import numpy as np

data = SplatData(100)
data.position[:, 0] = np.linspace(-5, 5, 100, dtype=np.float32)
data.color[:, 3] = 200  # set opacity
assert data.count == 100
assert data.position.shape == (100, 3)
assert data.color.shape == (100, 4)
```

### 6.2 Append Two Datasets

```python
d1 = SplatData(50)
d1.position[:, 0] = 1.0
d2 = SplatData(30)
d2.position[:, 0] = 2.0
d1.append(d2)
assert d1.count == 80
assert np.sum(d1.position[:, 0] == 1.0) == 50
assert np.sum(d1.position[:, 0] == 2.0) == 30
```

### 6.3 Splat Format Roundtrip

```python
from pygsbox.core.splat_data import SplatData, from_splat_format_bytes, to_splat_format_bytes
import numpy as np

data = SplatData(10)
data.position = np.random.randn(10, 3).astype(np.float32)
data.scale = np.random.randn(10, 3).astype(np.float32)
data.color = np.random.randint(0, 256, (10, 4), dtype=np.uint8)
data.rotation = np.random.randint(0, 256, (10, 4), dtype=np.uint8)

encoded = to_splat_format_bytes(data)
assert len(encoded) == 10 * 32

decoded = from_splat_format_bytes(encoded, 10)
assert np.allclose(decoded.position, data.position)
assert np.array_equal(decoded.color, data.color)
```

### 6.4 Alpha Filter

```python
data = SplatData(100)
data.color[:, 3] = np.random.randint(0, 256, 100, dtype=np.uint8)
filtered = data.filter_alpha(128)
assert filtered.count == np.sum(data.color[:, 3] >= 128)
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Columnar array storage and operations |
| `pygsbox.common.codec` | `encode_splat_color` etc. (used indirectly via formats) |

## 8. Agent Notes

- **NumPy columnar layout is non-negotiable** — never use list of dicts or list of objects
- **shape convention**: All arrays have shape (N, D) even when N=0
- **uint8 encoding**: Rotation, Color, SH are all uint8 with value 128 = "zero" in quaternion/float space
- **Position precision**: float32 is the canonical type; converting to float64 before ops, then back
- **Splat format**: 32 bytes exactly, no header, no count prefix — count inferred from `len(data) // 32`
- **Do not add per-splat metadata as new SplatData fields** — use the existing `flag_value`, `palette_idx`, `lod` spare fields

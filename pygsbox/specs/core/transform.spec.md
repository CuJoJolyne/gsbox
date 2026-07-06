# transform — Geometric Transformations

> Auto-generated code target: `core/transform.py`

## 1. Purpose

Apply rotation (Quaternion), scale, and translation to SplatData.  
Both positions and rotation quaternions are transformed.

## 2. Data Structures

### 2.1 Quaternion

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| x | float | 0.0 | i component |
| y | float | 0.0 | j component |
| z | float | 0.0 | k component |
| w | float | 1.0 | Real component (default = identity) |

Methods: `from_axis_angle(axis, angle)`, `length()`, `normalize()`, `premultiply(q)`, `_multiply_quaternions(a, b)` (static).

### 2.2 Vector3

| Field | Type | Purpose |
|-------|------|---------|
| x, y, z | float | 3D point |

Methods: `apply_quaternion(q)` — rotate vector by quaternion.

## 3. Public API

### 3.1 `translate(data: SplatData, tx: float, ty: float, tz: float) -> None`
- **Description**: Add offset to all positions.
- **Algorithm**: `data.position += (tx, ty, tz)` (numpy broadcast).
- **Edge Cases**: No-op when all offsets are 0.

### 3.2 `scale(data: SplatData, factor: float) -> None`
- **Description**: Multiply positions by factor. Adjust log-space scales by multiplying the exp-decoded values.
- **Algorithm**: 
  1. `data.position *= factor`
  2. `decoded_scales = exp(data.scale)` → `decoded_scales *= factor` → `data.scale = log(decoded_scales)`
- **Edge Cases**: factor=1.0 → no-op.

### 3.3 `rotate(data: SplatData, degree_x: float, degree_y: float, degree_z: float) -> None`
- **Description**: Rotate positions and rotation quaternions.
- **Algorithm**:
  1. Build axis-angle quaternions `qx`, `qy`, `qz` from degrees
  2. Compose: `q = qx * qy * qz` (premultiply, ZYX intrinsic = XYZ extrinsic)
  3. Apply `q` to each position via `Vector3.apply_quaternion(q)`
  4. Apply same axis quaternions to each rotation in data.rotation
  5. Re-normalize rot after multiply
- **Edge Cases**: All degrees=0 → no-op.

### 3.4 `transform(data, rotate_angles, scale_factor, translate_offset, order: str = "RST") -> None`
- **Description**: Apply R/S/T in specified order.
- **Order**: RST, RTS, SRT, STR, TRS, TSR (case insensitive).
- **Algorithm**: Dispatch table: `{'R': rotate, 'S': scale, 'T': translate}`.

## 4. Algorithm Details

### 4.1 Quaternion Premultiply

Given quaternions `a` and `b`, `a.premultiply(b)` = `b * a` (Hamilton product, `b` applied first):

```
new_x = b.x*a.w + b.w*a.x + b.y*a.z - b.z*a.y
new_y = b.y*a.w + b.w*a.y + b.z*a.x - b.x*a.z
new_z = b.z*a.w + b.w*a.z + b.x*a.y - b.y*a.x
new_w = b.w*a.w - b.x*a.x - b.y*a.y - b.z*a.z
```

### 4.2 Vector Rotation by Quaternion

```
ix = q.w*x + q.y*z - q.z*y
iy = q.w*y + q.z*x - q.x*z
iz = q.w*z + q.x*y - q.y*x
iw = -q.x*x - q.y*y - q.z*z

x' = ix*q.w + iw*(-q.x) + iy*(-q.z) - iz*(-q.y)
y' = iy*q.w + iw*(-q.y) + iz*(-q.x) - ix*(-q.z)
z' = iz*q.w + iw*(-q.z) + ix*(-q.y) - iy*(-q.x)
```

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| All transforms zero | No-op |
| factor=1.0 | No-op |
| Quaternion length=0 | Return identity quaternion |
| Rotation with no points | No-op |

## 6. Examples

### 6.1 Basic Transform

```python
from pygsbox.core.splat_data import SplatData
from pygsbox.core.transform import Quaternion, Vector3

q = Quaternion.from_axis_angle((0, 0, 1), 1.5708)  # 90° around Z
v = Vector3(1, 0, 0)
rotated = v.apply_quaternion(q)
assert abs(rotated.x) < 0.001 and abs(rotated.y - 1.0) < 0.001
```

### 6.2 Transform Pipeline

```python
from pygsbox.core import transform
data = SplatData(10)
data.position[:, 0] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
transform.rotate(data, 0, 0, 90)
transform.scale(data, 2.0)
transform.translate(data, 5, 0, 0)
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Vectorized array ops |
| `pygsbox.common.codec` | `deg_to_rad`, `clip_float32`, `decode_splat_rotation`, `encode_splat_rotation` |

## 8. Agent Notes

- **Per-point rotation loop is known bottleneck**: The `rotate` function loops over `data.count` for quaternion application. This should eventually be vectorized with numpy batch quaternion multiplication.
- **Quaternion normalization**: After any composition, call `.normalize()` to prevent accumulated drift.
- **Rotation re-normalization**: After applying axis rotations to splat quaternions, re-normalize via `_normalize_rotations()`.
- **Scale transform**: Must decode scale from log-space, scale the exp value, re-encode. Do NOT multiply log-space directly.

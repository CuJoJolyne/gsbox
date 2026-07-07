# codec — Encoding/Decoding Functions

> Auto-generated code target: `common/codec.py`

## 1. Purpose

Bit-level encoding/decoding for 3DGS attributes used across all 7 formats:
- Position: 24-bit signed fixed-point (<-> float32)
- Scale: log-space byte (<-> float32)
- Color: SH-aware byte encoding (<-> float32 physical value)
- Opacity: sigmoid byte (<-> float32 logit)
- Rotation: quaternion normalization, NQ packed format, SOG packed format
- Spherical Harmonics (SH): float32 <-> uint8 quantization

All functions are **pure** (no I/O, no state), working on scalars or bytes.

## 2. Data Structures

None. This module contains only pure functions.

## 3. Constants

| Name | Value | Purpose |
|------|-------|---------|
| `SH_C0` | 0.28209479177387814 | SH band-0 constant for color ↔ DC conversion |
| `COLOR_SCALE` | 0.15 | SPZ color encoding scale factor |
| `SQRT1_2` | 0.7071067811865476 | 1/√2, used in NQ rotation encoding |
| `SQRT2` | 1.4142135623730951 | √2 |
| `CMask` | 511 (0x1FF) | 9-bit mask for NQ rotation magnitude |
| `DEG2RAD` | π/180 | Degree to radian conversion |
| `RAD2DEG` | 180/π | Radian to degree conversion |

## 4. Public API

### 4.1 Clipping Functions

#### `clip_uint8(val: float) -> int`
- **Description**: Clamp and convert to uint8 [0, 255]
- **Algorithm**: `int(max(0, min(255, val)))`

#### `clip_float32(val: float) -> float`
- **Description**: Clamp to float32 representable range
- **Algorithm**: `max(-3.4e38, min(3.4e38, val))`

### 4.2 Position Encoding (SPZ / SPX)

#### `spz_encode_position(val: float) -> bytes`
- **Description**: Encode float32 position to 3-byte 24-bit signed fixed-point (scale=4096)
- **Algorithm**:
  ```
  fixed32 = int(round(val * 4096)) & 0xFFFFFF
  return bytes([fixed32 & 0xFF, (fixed32 >> 8) & 0xFF, (fixed32 >> 16) & 0xFF])
  ```

#### `spz_decode_position(b: bytes, fractional_bits: int = 12) -> float`
- **Description**: Decode 3-byte 24-bit signed fixed-point to float32
- **Preconditions**: `len(b) >= 3`, `fractional_bits == 12` (only supported value)
- **Algorithm**:
  ```
  scale = 1.0 / 4096
  fixed32 = b[0] | (b[1] << 8) | (b[2] << 16)
  if fixed32 & 0x800000: fixed32 |= -0x1000000  # sign-extend 24-bit to 32-bit
  return clip_float32(fixed32 * scale)
  ```

#### `encode_spx_position_uint24(val: float) -> bytes`
- Same algorithm as `spz_encode_position` — both produce 24-bit fixed-point.

#### `decode_spx_position_uint24(b0: int, b1: int, b2: int) -> float`
- Same as `spz_decode_position` but takes individual bytes instead of bytes object.

### 4.3 Scale Encoding

#### `spz_encode_scale(val: float) -> int`
- **Description**: Encode log-space scale to uint8 [0, 255]
- **Algorithm**: `clip_uint8_round((val + 10.0) * 16.0)`
- **Range**: val ∈ [-10, +5.9375]

#### `spz_decode_scale(val: int) -> float`
- **Description**: Decode uint8 back to log-space scale
- **Algorithm**: `val / 16.0 - 10.0`

#### `encode_spx_scale(val: float) -> int`
- Same as `spz_encode_scale`.

#### `decode_spx_scale(val: int) -> float`
- Same as `spz_decode_scale`.

#### `encode_splat_scale(val: float) -> float`
- **Description**: Convert log-space scale to linear scale (exp)
- **Algorithm**: `clip_float32(exp(val))`

#### `decode_splat_scale(encoded_val: float) -> float`
- **Description**: Convert linear scale to log-space (log)
- **Algorithm**: `clip_float32(ln(encoded_val))`

### 4.4 Color Encoding

#### `spz_encode_color(val: int) -> int`
- **Description**: Encode uint8 color (splat-space) to SPZ packed uint8
- **Algorithm**: `f_color = (val/255.0 - 0.5) / SH_C0; return uint8(f_color * COLOR_SCALE * 255 + 0.5*255)`

#### `spz_decode_color(val: int) -> int`
- **Description**: Decode SPZ packed uint8 back to splat-space uint8
- **Algorithm**: `f_color = (val - 0.5*255) / (COLOR_SCALE * 255); return uint8((0.5 + SH_C0 * f_color) * 255)`

#### `encode_splat_color(val: float) -> int`
- **Description**: Encode physical SH coefficient to uint8 color
- **Algorithm**: `clip_uint8((0.5 + SH_C0 * val) * 255.0)`

#### `decode_splat_color(val: int) -> float`
- **Description**: Decode uint8 color to physical SH coefficient
- **Algorithm**: `clip_float32((val/255.0 - 0.5) / SH_C0)`

### 4.5 Opacity Encoding

#### `encode_splat_opacity(val: float) -> int`
- **Description**: Encode logit opacity to uint8 via sigmoid
- **Algorithm**: `clip_uint8(1.0 / (1.0 + exp(-val)) * 255.0)`

#### `decode_splat_opacity(val: int) -> float`
- **Description**: Decode uint8 to logit opacity via inverse sigmoid.
- **Algorithm**: `v = val / 255.0`; if v >= 1.0 return +inf; if v <= 0.0 return -inf; else `return -ln(1.0/v - 1.0)` (the logit function).
- **Edge Cases**: val=255 → +infinity (logit of 1.0), val=0 → -infinity (logit of 0.0).

### 4.6 Rotation Encoding

#### `spz_encode_rotations_v3v4(rw, rx, ry, rz: int) -> bytes`
- **Description**: Encode 4 uint8 quaternion components to 4-byte NQ packed format (SPZ v3/v4)
- **Algorithm**:
  1. Normalize quaternion by dividing each component by length
  2. Find index of largest absolute component
  3. If that component < 0, negate all components
  4. For each of the 3 non-largest components:
     - `sign = 1 if comp < 0 else 0`
     - `mag = int(CMask * abs(comp) / SQRT1_2 + 0.5)`
     - `encoded = (sign << 9) | mag`
  5. Pack: `result = index << 30 | enc[0] | enc[1] << 10 | enc[2] << 20`
  6. Return 4 bytes (little-endian uint32)

#### `spz_decode_rotations_v3v4(bs: bytes) -> Tuple[int, int, int, int]`
- **Description**: Decode 4-byte NQ packed format to 4 uint8 quaternion components
- **Algorithm**: Reverse of encode — extract index (bits 31-30), decode 3 components (10 bits each), compute 4th via `sqrt(1 - sum_squares)`, convert back to uint8.

#### `spz_encode_rotations(rw, rx, ry, rz: int) -> bytes`
- **Description**: Encode 4 uint8 quaternion to 3-byte packed format (SPZ v2, older).
- **WARNING**: This encoding is **lossy** — the dropped component's identity and sign are NOT stored. Decode always assumes `r0` was the largest positive component. Only use when w component is known to be dominant.
- **Algorithm**:
  1. Convert uint8 → float [-1, 1]: `r_i = val_i / 128.0 - 1.0` for i in 0..3
  2. Normalize: divide all 4 components by `qlen = sqrt(r0² + r1² + r2² + r3²)`
  3. Find index of largest absolute component: `idx = argmax_i(|r_i|)`
  4. Discard `r[idx]`, keep the other 3 in original order
  5. For each kept component: `v = abs(r) / SQRT1_2` → `uint8 = clip_uint8(round(v * 255.0))`
  6. Return 3 bytes (index and sign are lost)

#### `spz_decode_rotations(b0, b1, b2: int) -> Tuple[int, int, int, int]`
- **Description**: Decode 3-byte packed format to 4 uint8 quaternion.
- **Algorithm**:
  1. Treat bytes as r1, r2, r3 (assumes r0 was the dropped component)
  2. Scale: `r1 = b0 / 255.0 * SQRT1_2`, `r2 = b1 / 255.0 * SQRT1_2`, `r3 = b2 / 255.0 * SQRT1_2`
  3. Derive r0 (assumed largest, always positive): `r0 = sqrt(max(0.0, 1.0 - r1² - r2² - r3²))`
  4. Convert to uint8: `uint8 = clip_uint8(r * 128.0 + 128.0)` for each of r0, r1, r2, r3
- **Edge Cases**: If `r1² + r2² + r3² >= 1.0`, then r0=0 (clamped). The result is still a valid quaternion if the input had r0 as the genuine largest positive component.

#### `decode_spx_rotations(rx, ry, rz: int) -> Tuple[int, int, int, int]`
- **Description**: Decode 3-byte SPX rotation to 4 uint8 quaternion
- **Algorithm**: `r1 = rx/128 - 1`, `r2 = ry/128 - 1`, `r3 = rz/128 - 1`, `r0 = sqrt(max(0, 1 - sum_sq))`, convert to uint8.

#### `sog_encode_rotations(rw, rx, ry, rz: int) -> Tuple[int, int, int, int]`
- **Description**: Encode 4 uint8 quaternion to SOG RGBA format
- **Algorithm**: Normalize to float64 → find largest component → encode other 3 as `uint8((val/SQRT2 + 0.5) * 255)` → use index+252 as alpha channel.

#### `sog_decode_rotations(r0, r1, r2, ri: int) -> Tuple[int, int, int, int]`
- **Description**: Decode SOG RGBA format to 4 uint8 quaternion
- **Algorithm**: Decode 3 float components from `(val/255 - 0.5) * SQRT2`, compute 4th from `sqrt(1 - sum_sq)`, reorder based on alpha index, convert to uint8.

### 4.7 SH Encoding

#### `encode_splat_sh(val: float) -> int`
- **Description**: Encode physical SH coefficient (float) to uint8
- **Algorithm**: `clip_uint8(round(val * 128.0) + 128.0)`

#### `decode_splat_sh(val: int) -> float`
- **Description**: Decode uint8 to physical SH coefficient
- **Algorithm**: `(val - 128.0) / 128.0`

#### `encode_spx_sh(val: int) -> int`
- **Description**: Quantize SH uint8 with step size 8 (SPX format)
- **Algorithm**: `clip_uint8(floor((val + 4.0) / 8.0) * 8.0)`

#### `spz_encode_sh1(val: int) -> int`
- **Description**: Quantize SH uint8 with step size 8 (SPZ SH degree 1)
- **Algorithm**: Same as `encode_spx_sh`.

#### `spz_encode_sh23(val: int) -> int`
- **Description**: Quantize SH uint8 with step size 16 (SPZ SH degree 2/3)
- **Algorithm**: `clip_uint8(floor((val + 8.0) / 16.0) * 16.0)`

### 4.8 Log/Exp Encoding

#### `encode_log(value: float, times: int = 1) -> float`
- **Description**: Apply log transform `times` times for position compression
- **Algorithm**: `log(|value| + 1)`, signed. Apply recursively if times > 1.

#### `decode_log(encoded: float, times: int = 1) -> float`
- **Description**: Undo log transform
- **Algorithm**: `exp(|encoded|) - 1`, signed. Apply recursively if times > 1.

#### `sog_encode_log(value: float) -> float`
- **Description**: Log transform for SOG position encoding
- **Algorithm**: Same as `encode_log(x, 1)`.

### 4.9 Utility

#### `hash_bytes(bts: bytes, init_val: int = 53653) -> int`
- **Description**: Simple rolling hash for SPX header integrity check
- **Algorithm**: `for b in bytes: rs = ((rs * 33) ^ b) & 0xFFFFFFFF`

#### `decode_float16(encoded: int) -> float`
- **Description**: Decode IEEE 754 half-precision float to float32.
- **Algorithm**: Extract sign (bit 15), exponent (bits 10-14, 5 bits), mantissa (bits 0-9, 10 bits). Handle 4 cases:
  1. exponent=0, mantissa=0: return ±0.0
  2. exponent=0, mantissa≠0: subnormal → `(-1)^sign × 2^(-14) × m/1024`
  3. exponent=0x1F, mantissa=0: return ±inf
  4. exponent=0x1F, mantissa≠0: return NaN
  5. else: normal → `(-1)^sign × 2^(exponent-15) × (1 + m/1024)`
- **Used by**: KSplat reader (compression mode 1/2)

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `decode_spx_scale(0)` | Returns -10.0 |
| `decode_spx_scale(255)` | Returns ~5.9375 |
| `spz_decode_position(b'\xff\xff\x7f', 12)` | Returns ~8.3886 (max positive for 24-bit/12frac scale) |
| `spz_decode_position(b'\x00\x00\x80', 12)` | Returns ~-8.3886 (max negative) |
| `encode_splat_opacity(inf)` | Returns 255 |
| `encode_splat_opacity(-inf)` | Returns 0 |
| NQ rotation: all components 128 | identity quaternion, largest component at index 0 or 3 |
| `decode_float16(0x0000)` | Returns 0.0 |
| `decode_float16(0x7C00)` | Returns +inf |
| `hash_bytes(b'')` | Returns init_val (53653) |
| `encode_log(0, 1)` | Returns 0.0 |
| `decode_log(0, 1)` | Returns 0.0 |
| `decode_splat_opacity(255)` | Returns +inf (logit of 1.0) |
| `decode_splat_opacity(0)` | Returns -inf (logit of 0.0) |

## 6. Examples

### 6.1 Position Roundtrip

```python
from pygsbox.common.codec import spz_encode_position, spz_decode_position

original = 3.5
encoded = spz_encode_position(original)
decoded = spz_decode_position(encoded)
assert abs(decoded - original) < 0.001  # 24-bit precision
```

### 6.2 NQ Rotation Roundtrip

```python
from pygsbox.common.codec import spz_encode_rotations_v3v4, spz_decode_rotations_v3v4

rw, rx, ry, rz = 200, 100, 80, 150
packed = spz_encode_rotations_v3v4(rw, rx, ry, rz)
assert len(packed) == 4
drw, drx, dry, drz = spz_decode_rotations_v3v4(packed)
# NQ encoding loses ~2 LSBs — values should be close
assert all(0 <= v <= 255 for v in (drw, drx, dry, drz))
```

### 6.3 Scale Roundtrip

```python
from pygsbox.common.codec import spz_encode_scale, spz_decode_scale

for v in [-5.0, 0.0, 2.0]:
    e = spz_encode_scale(v)
    d = spz_decode_scale(e)
    assert abs(d - v) < 0.1
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| math | exp, log, sqrt, floor, ceil |
| struct | pack/unpack IEEE float |
| numpy | finfo for float32 limits |

## 8. Agent Notes

- **命名约定**: `encode_X` takes native value → encoded bytes/int; `decode_X` takes encoded bytes/int → native value
- **精度**: 24-bit 定点误差 < 0.001 (2^-12); NQ 旋转误差 ~2-5 quanta; uint8 颜色误差 <= 1
- **性能要求**: 所有函数是标量纯函数，进入热路径时调用方负责向量化（用 numpy 批量处理）
- **不要手写循环向量化版本**: codec 保持标量，向量化在 reader/writer 层做
- **可选依赖**: 无插件依赖——只用标准库 + numpy

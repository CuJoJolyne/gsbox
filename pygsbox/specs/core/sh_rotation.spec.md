# sh_rotation — Spherical Harmonics Rotation

> Auto-generated code target: `core/sh_rotation.py`

## 1. Purpose

Apply rotation to spherical harmonics (SH) coefficients using Wigner D-matrices. When a 3DGS model is rotated, the SH coefficients must be transformed to match — this is more complex than just rotating positions because SH encodes directional information.

## 2. Data Structures

### 2.1 SHRotation

Wraps precomputed Wigner D-matrices for bands 1-3. Supports rotation by Euler angles (ZYZ or ZXZ convention).

## 3. Public API

### 3.1 `class SHRotation`

#### `__init__(self, alpha: float, beta: float, gamma: float, convention: str = 'ZYZ')`
- **Description**: Build D-matrices for bands 1-3 from Euler angles.
- **Algorithm**: Compute d-matrices (3x3 for band 1, 5x5 for band 2, 7x7 for band 3) using Wigner small-d formula, then multiply by phase factors from D = e^(-im'*alpha) * small_d * e^(-im*gamma).

#### `rotate(self, data: SplatData) -> None`
- **Description**: Apply stored D-matrices to data.sh coefficients.
- **Algorithm**:
  1. For each band b in [1,2,3]:
     - Extract SH coefficients for that band (shape: N × 3 × (2*b+1))
     - Unpack uint8 to float32
     - Apply D-matrix: `sh_rotated = sh @ D.T` for each color channel
     - Repack to uint8
  2. Band 0 (ambient) is rotation-invariant — no change.

## 4. Edge Cases

| Scenario | Behavior |
|----------|----------|
| alpha=beta=gamma=0 | Identity rotation, no-op |
| SH degree=0 | No bands to rotate, no-op |

## 5. Examples

```python
from pygsbox.core.sh_rotation import SHRotation

rot = SHRotation(alpha=1.57, beta=0.0, gamma=0.0)  # 90° rotation
rot.rotate(data)  # in-place SH coefficient transform
```

## 6. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Matrix multiplication |
| math | sin, cos |

## 7. Agent Notes

- **Wigner d-matrix**: Reference implementation from [Wikipedia Wigner D-matrix](https://en.wikipedia.org/wiki/Wigner_D-matrix). Band 1 d-matrix is 3x3, band 2 is 5x5, band 3 is 7x7.
- **SH layout**: `data.sh[i, 0:9]` = band 1 (RGB×3), `9:24` = band 2 (RGB×5), `24:45` = band 3 (RGB×7).
- **Rotation convention**: ZYZ Euler angles — alpha=azimuth pre-rotation, beta=polar, gamma=azimuth post-rotation.
- **uint8 ↔ float32**: SH coefficients stored as uint8 (128 = 0.0), convert to float before matrix multiply, convert back after.

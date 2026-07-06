# obj — Wavefront OBJ Vertex Transform

> Auto-generated code target: `formats/obj.py`

## 1. Purpose

Apply rotation/scale/translation to vertex positions in `.obj` files.  
Only transforms lines starting with `v ` (vertex positions), passes other lines through unchanged.

## 2. Public API

### `obj_transform(src: str, dst: str, degree_x=0, degree_y=0, degree_z=0, scale_factor=1.0, tx=0, ty=0, tz=0, order="rst") -> None`
- **Description**: Transform vertices in OBJ file.
- **Algorithm**:
  1. Open src → read line by line
  2. For lines starting with `v `:
     a. Parse `x y z` floats
     b. Apply transforms in specified order: R(quaternion axis-angle), S(multiply), T(add)
     c. Write `v {nx:.6f} {ny:.6f} {nz:.6f}\n`
  3. Other lines: write unchanged

## 3. Transform Order

| Code | Sequence |
|------|----------|
| rst | rotate → scale → translate (default) |
| rts | rotate → translate → scale |
| srt | scale → rotate → translate |
| str | scale → translate → rotate |
| trs | translate → rotate → scale |
| tsr | translate → scale → rotate |

## 4. Examples

```python
from pygsbox.formats.obj import obj_transform

obj_transform("input.obj", "output.obj", degree_z=90, scale_factor=2.0)
# (1,0,0) → rotate Z90 → (0,1,0) → scale×2 → (0,2,0)
```

## 5. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.core.transform` | Quaternion, Vector3 |
| `pygsbox.common.codec` | deg_to_rad, clip_float32 |

## 6. Agent Notes

- **Only vertex lines**: The Go version only transforms "v " lines. Do not transform "vn" or "vt" lines.
- **Precision**: 6 decimal places, matching Go's `fmt.Sprintf("v %.6f %.6f %.6f")`.
- **Transform order**: Lowercase in API, can be uppercase internally.

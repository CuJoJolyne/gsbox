# ply — PLY Format Reader/Writer

> Auto-generated code target: `formats/ply.py`

## 1. Purpose

Read/write PLY format, supporting three variants:
- **Official 3DGS PLY**: Standard `binary_little_endian 1.0` with f_dc/opacity/scale/rot/SH
- **Compressed PLY**: SuperSplat chunk-based with 11-10-11 packed fields
- **RGB PLY**: Simple x/y/z + red/green/blue point cloud

## 2. Data Structures

### 2.1 PlyHeader

| Field | Type | Purpose |
|-------|------|---------|
| declare | str | "ply" |
| format | str | "binary_little_endian 1.0" |
| vertex_count | int | Number of vertices |
| chunk_count | int | Number of chunks (compressed PLY only) |
| header_length | int | Bytes before binary data starts |
| row_length | int | Bytes per vertex row |
| comment | str | Comment from header |
| text | str | Full header text |
| map_offset | dict | Property name → byte offset in row |
| map_type | dict | Property name → type string |

### 2.2 _CompressedChunk

18 float32 values defining per-chunk min/max ranges:
min/max for x, y, z, scale_x, scale_y, scale_z, r, g, b.

### 2.3 Detection Methods

- `is_official_ply()`: Has f_dc_0/1/2, opacity, scale_0/1/2, rot_0/1/2/3
- `is_compressed_ply()`: Has chunk element + packed_* properties
- `is_rgb_ply()`: Has x/y/z + red/green/blue

## 3. Public API

### 3.1 `read_ply(file_path: str) -> Tuple[PlyHeader, SplatData]`
- **Description**: Detect PLY type and dispatch to appropriate reader.
- **Dispatch order**: compressed → official → RGB → error

### 3.2 `write_ply(file_path: str, data: SplatData, comment: str = "", sh_degree: int = 0) -> None`
- **Description**: Write official 3DGS PLY. Per-row: xyz(float32×3), f_dc×3, [f_rest×N], opacity, scale×3, rot×4.
- **SH order**: Write `f_rest` in official channel-major order. For each channel R/G/B, write all bases from internal `data.sh[:, basis*3+channel]`.

### 3.3 `write_compressed_ply(file_path: str, data: SplatData, sh_degree: int = 0, comment: str = "") -> None`
- **Description**: Write SuperSplat compressed PLY with 256-splat chunks.

## 4. Official PLY Reader (Vectorized)

```
1. Parse header → determine row_length and vertex_count
2. Build structured numpy dtype from header property offsets
3. np.frombuffer(raw_data, dtype=..., count=vertex_count)
4. Extract position, color (encode via SH_C0), opacity (sigmoid), scale (log), rotation (normalize)
5. If SH: convert official PLY channel-major `f_rest` order into internal basis-major `SplatData.sh` order: `data.sh[:, basis*3+channel] = encode_splat_sh(f_rest_{basis + channel*sh_dim})`. Fill unused SH slots with 128.
```

## 5. Compressed PLY Format

### 5.1 File Layout

```
Header (text) → Chunk metadata (72B × N) → Splat data (16B × M) → [SH data]
```

### 5.2 Splat Data (16 bytes)

| Offset | Size | Type | Content |
|:------:|:---:|------|---------|
| 0 | 4 | uint32 | packed_position (11:10:11 X:Y:Z) |
| 4 | 4 | uint32 | packed_rotation (NQ: 2b index + 3×10b components) |
| 8 | 4 | uint32 | packed_scale (11:10:11) |
| 12 | 4 | uint32 | packed_color (8:8:8:8 RGBA) |

## 6. Compressed PLY Reader

```
1. Parse header
2. Read chunk metadata: 18 float32s per chunk
3. For each chunk (256 splats except last remainder):
   - Read 256 × 16 bytes of splat data
   - For each splat: unpack position (11-10-11), rotation (NQ), scale, color (RGBA denorm)
4. If SH properties exist: read (3×shDim) bytes per splat after all splat data
```

## 7. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Unknown PLY type | ValueError("Unsupported PLY format") |
| Header too long | Expand read buffer |
| Compressed PLY: last chunk < 256 | Read remainder |
| Compressed PLY: no SH | Skip SH parsing |
| RGB PLY: no SH/scale/rotation | Fill defaults (-4.6 scale, identity rot, 255 alpha) |
| Official PLY: missing f_rest | max_sh_degree=0 |

## 8. Examples

```python
from pygsbox.formats.ply import read_ply, write_ply, write_compressed_ply

# Official PLY roundtrip
write_ply("test.ply", data, sh_degree=1)
hdr, decoded = read_ply("test.ply")
assert decoded.count == data.count

# Compressed PLY roundtrip
write_compressed_ply("test_comp.ply", data)
hdr, decoded = read_ply("test_comp.ply")
assert hdr.is_compressed_ply()
```

## 9. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.codec` | encode_splat_color/opacity, decode_splat_scale, normalize_rotations |
| numpy, struct, math | Vectorized parsing, binary packing |

## 10. Agent Notes

- **Property order matters**: Official PLY properties are ordered x,y,z,f_dc_0/1/2,opacity,scale_0/1/2,rot_0/1/2/3. The header parser sorts by offset, so any order works.
- **Scale encoding**: Official PLY stores log-space scale (exp in Go, ln in reader). Compressed PLY stores linear scale.
- **Rotation normalization**: Official PLY normalizes raw float quaternion to unit length before uint8 encoding. Compressed PLY uses NQ format directly.
- **Vectorized reader is critical**: Don't use per-row Python loops for official PLY — the structured dtype approach gives 100x speedup.

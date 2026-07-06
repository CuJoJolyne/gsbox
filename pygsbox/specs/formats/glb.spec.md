# glb — glTF Binary (KHR_gaussian_splatting) Reader/Writer

> Auto-generated code target: `formats/glb.py`

## 1. Purpose

Read/write GLB files with `KHR_gaussian_splatting` or `KHR_gaussian_splatting_compression_spz_2` or `com_github_gotoeasy_gsbox_webp_rgb_ply` extensions.

## 2. GLB Container Structure

```
Header:  gLTF (magic) | uint32(2=version) | uint32(file_length)
Chunk0:  uint32(json_length) | "JSON" | json_bytes | padding to 4B
Chunk1:  uint32(bin_length) | "BIN\0" | bin_bytes | padding to 4B
```

## 3. Supported Extensions

### 3.1 KHR_gaussian_splatting (read/write)

Full float32 attribute arrays in BIN chunk:
| Attribute | Size | Type | Accessor |
|-----------|:---:|------|----------|
| POSITION | N×12 | VEC3 float | accessor[0] |
| COLOR_0 | N×4 | VEC4 uint8 | accessor[1] |
| ROTATION | N×16 | VEC4 float | accessor[2] |
| SCALE | N×12 | VEC3 float | accessor[3] |
| OPACITY | N×4 | SCALAR float | accessor[4] |
| SH_DEGREE_0_COEF_0 | N×12 | VEC3 float | accessor[5] |
| SH_DEGREE_1_COEF_0..2 | N×12 each | VEC3 float | accessor[6-8] |
| SH_DEGREE_2_COEF_0..4 | N×12 each | VEC3 float | accessor[9-13] |
| SH_DEGREE_3_COEF_0..6 | N×12 each | VEC3 float | accessor[14-20] |

JSON schema: `meshes[0].primitives[0].attributes`, `accessors[]`, `bufferViews[]`.

### 3.2 KHR_gaussian_splatting_compression_spz_2 (read/write)

BIN chunk contains a gzip-compressed SPZ v3 blob. JSON schema references a single `bufferView` with `"KHR_gaussian_splatting_compression_spz_2": {"bufferView": 0}`.

### 3.3 com_github_gotoeasy_gsbox_webp_rgb_ply (read/write)

BIN chunk contains a WebP-compressed RGB point cloud. Encoded as: 4-byte count header + 4 RGBA channels (3 position byte-planes + color).

## 4. Public API

### 4.1 `read_glb(file_path: str) -> Tuple[int, SplatData]`
- **Description**: Parse GLB header → check extension in JSON → dispatch to appropriate reader.
- **Returns**: `(sh_degree, SplatData)`

### 4.2 `write_glb(file_path, data: SplatData, sh_degree=0, glb_extension="KHR_gaussian_splatting") -> None`
- **Description**: Write GLB with specified extension.

## 5. Algorithm (KHR_gaussian_splatting reader)

```
1. Read file header: magic("glTF"), version(2), total_length
2. Read JSON chunk: json_length, json_string
3. Check: KHR_gaussian_splatting in extensionsUsed/Required
4. Extract attribute accessor indices from meshes[0].primitives[0].attributes
5. Extract byte offsets from bufferViews[index]
6. Read BIN chunk header
7. Read accessor[0].count = splat_count
8. For each splat: read position(12B), color(4B), rotation(16B), scale(12B), opacity(4B), sh0(12B)
9. Determine sh_degree by finding highest SH accessor index present
10. Read SH coefficients per degree if present
11. Convert float32 values to SplatData uint8 encoding
```

## 6. Edge Cases

| Scenario | Behavior |
|----------|----------|
| No KHR_gaussian_splatting extension | `ValueError("Unsupported GLB extension")` |
| Missing POSITION attribute | `ValueError("unsupported glb")` |
| SH degree = 0 | No SH accessors present |
| SH degree = 1 | accessor[6-8] present |
| BIN chunk not 4-byte aligned | Read binLength bytes, padding after |

## 7. Examples

```python
from pygsbox.formats.glb import write_glb, read_glb

write_glb("model.glb", data, sh_degree=1)
sh_deg, decoded = read_glb("model.glb")
assert decoded.count == data.count
assert sh_deg == 1
```

## 8. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.compress` | WebP decompress (RGB PLY extension) |
| `pygsbox.common.codec` | encode_splat_color, encode_splat_opacity, etc. |
| `pygsbox.core.morton` | sort_morton (RGB PLY writer) |
| json, struct | JSON chunk parsing, binary packing |

## 9. Agent Notes

- **JSON chunk 4-byte alignment**: Use `(json_length + 3) & ~3`. Padding bytes after JSON are spaces, not nulls.
- **BIN chunk**: Actual data length may differ from aligned length. The padding bytes are `0x00`.
- **SH interleaving**: In the BIN buffer, SH coefficients are stored with per-degree RGB triplets at 12-byte strides. The reader reconstructs them into SplatData.sh[] layout.
- **SPZ extension**: For write, generate SPZ v3 bytes first, then embed as single gzip blob in BIN.

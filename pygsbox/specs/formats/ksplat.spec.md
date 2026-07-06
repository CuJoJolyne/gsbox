# ksplat — KSplat Format Reader

> Auto-generated code target: `formats/ksplat.py`

## 1. Purpose

Read-only KSplat format (version 0.1). Supports 3 compression modes with spatial bucket organization.

## 2. File Layout

| Section | Size | Content |
|---------|------|---------|
| Main header | 4096 B | Version, counts, compression mode, harmonics range |
| Section headers | 1024 B × N | Per-section bucket info, sh_degree |
| Bucket metadata | variable | Partial bucket sizes (4B each) |
| Bucket centers | S×12 B | XYZ float32 for each bucket |
| Splat data | variable | S×B_size bytes per section |

## 3. Compression Modes

| Mode | Position | Scale | Rotation | Color | Harmonics |
|:----:|:--------:|:-----:|:--------:|:-----:|:---------:|
| 0 | float32×3 | float32×3 | float32×4 | uint8×4 | float32 |
| 1 | uint16×3(quantized) | float16×3 | float16×4 | uint8×4 | float16 |
| 2 | uint16×3(quantized) | float16×3 | float16×4 | uint8×4 | uint8(quantized) |

Position decoding (modes 1/2): `(uint16_val - quant_range) * block_size/2/quant_range + bucket_center`

## 4. Public API

### `read_ksplat(file_path: str) -> Tuple[KsplatHeader, SplatData]`
- **Description**: Read KSplat file, return header and data.
- **Returns**: KsplatHeader (0.1), SplatData

## 5. Algorithm

```
1. Read 4096B main header
2. Read N × 1024B section headers, determine max sh_degree
3. For each section:
   a. Read partial bucket sizes (4B × partial_count)
   b. Read bucket centers (12B × bucket_count)
   c. Read splat data (bytes_per_splat × section_capacity)
   d. For each splat:
      - Decode position (mode 0: float32 direct; mode 1/2: quantized + bucket)
      - Decode scale (mode 0: float32 decode; mode 1/2: float16 decode)
      - Decode rotation (float32/float16 to uint8)
      - Decode color (uint8×4)
      - Decode harmonics (float32/float16/uint8 quantized, interleaved with sh_index map)
4. Return (header, data)
```

## 6. SH Index Mapping

KSplat stores SH coefficients in a specific interleaved order (not sequential). The `sh_index` lookup table maps KSplat's storage order to SplatData.sh[] order:

```python
sh_indices = [
    0,3,6, 1,4,7, 2,5,8,          # Band 1
    9,14,19, 10,15,20, ..., 13,18,23,  # Band 2
    24,31,38, 25,32,39, ..., 30,37,44  # Band 3
]
```

## 7. Examples

```python
from pygsbox.formats.ksplat import read_ksplat
hdr, data = read_ksplat("model.ksplat")
print(f"v{hdr.major_version}.{hdr.minor_version}: {data.count} splats, SH={hdr.sh_degree}")
```

## 8. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.codec` | decode_splat_scale, encode_splat_rotation, decode_float16, encode_splat_sh |

## 9. Agent Notes

- **Read-only**: No writer. Go version doesn't write KSplat either.
- **SH index mapping is non-trivial**: Use the lookup table verbatim. The interleaving is baked into KSplat format.
- **Bucket indices**: Full buckets (capacity-sized) come first, then partial buckets. Track current bucket across the splat loop.

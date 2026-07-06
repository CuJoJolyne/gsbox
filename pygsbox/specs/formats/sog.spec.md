# sog — PlayCanvas SOG Format Reader/Writer

> Auto-generated code target: `formats/sog.py`

## 1. Purpose

Read/write PlayCanvas SOG format, a multi-file WebP-based compression format.  
Supports v1 (min/max range quantization) and v2 (codebook-based).

## 2. File Structure

Each SOG is a directory (or .sog zip archive) containing:

| File | Content |
|------|---------|
| `meta.json` | Metadata: version, count, bounds, codebooks |
| `means_l.webp` | Position (low byte of uint16), RGBA |
| `means_u.webp` | Position (high byte of uint16), RGBA |
| `scales.webp` | Scale (uint8), RGBA |
| `quats.webp` | Rotation (SOG packed), RGBA |
| `sh0.webp` | Color/Alpha, RGBA |
| `shN_centroids.webp` | SH palette centroids |
| `shN_labels.webp` | Per-point palette indices |

## 3. Data Structures

### 3.1 SogMeta (from meta.json)

Top-level JSON structure with means, scales, quats, sh0, shN sections. Each has codebook/min/max/files arrays.

### 3.2 Key v1 vs v2 Differences

| Feature | v1 | v2 |
|---------|:--:|:--:|
| Scale encoding | min/max range | 256-entry codebook |
| SH0 encoding | min/max range per channel | 256-entry codebook |
| shN codebook | Float codebook | Same codebook, explicit count/bands fields |
| meta.json keys | shape, dtype, mins, maxs | count, codebook |

## 4. Position Encoding

### 4.1 Writer

```
1. Compute log_min/max: sog_encode_log all positions
2. Per splat: normalize to [0,65535]:
   x = uint16(65535 * (log_val - min) / (max - min) + 0.5)
3. Split into low/high bytes:
   means_l[i*4+{0,1,2}] = x_lo, y_lo, z_lo
   means_u[i*4+{0,1,2}] = x_hi, y_hi, z_hi
   alpha channel = 255
4. Compress each as WebP
```

### 4.2 Reader

```
1. Decompress means_l/u WebP
2. Per splat: reconstruct uint16 = u << 8 | l
3. Normalize: f = uint16 / 65535.0
4. Denormalize: x = mins + (maxs - mins) * f
5. Decode log: decode_log(x)
```

## 5. Rotation (SOG Packed)

4 bytes RGBA where R,G,B encode 3 quaternion components via SQRT_2 scaling, and A = index+252 indicates which component was omitted.

## 6. SH Centroids (v2)

- centroids WebP: width depends on sh_degree (96/512/960), height=1024
- Each centroid is `sh_dim` pixels wide (sh_dim = 3/8/15)
- Labels WebP: auto-dimensioned, each pixel stores uint16 palette_idx in R/G channels

## 7. Public API

### 7.1 `read_sog(path: str) -> Tuple[SogHeader, SplatData]`
- **Description**: Detect .sog (unzip first) or meta.json directory, parse meta, dispatch to v1 or v2 reader.

### 7.2 `write_sog(path: str, data: SplatData, sh_degree: int = 0, as_zip: bool = True) -> None`
- **Description**: Write SOG v2. If as_zip=True, creates .sog archive; else writes meta.json + WebP files in directory.

## 8. Examples

```python
from pygsbox.formats.sog import read_sog, write_sog

write_sog("output.sog", data, sh_degree=1)
hdr, decoded = read_sog("output.sog")
assert decoded.count == data.count
```

## 9. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.compress` | WebP compress/decompress, ZIP |
| `pygsbox.common.codec` | sog_encode_log, sog_decode_rotations |
| `pygsbox.advanced.kmeans` | rewrite_sh_by_kmeans (for SH write) |
| json | meta.json parsing |

## 10. Agent Notes

- **.sog is a zip file**: Check extension first. If `.sog`, unzip to temp dir, then read `meta.json`.
- **SOG rotation differs from other formats**: Uses `sog_encode_rotations` (index+252), not NQ encoding.
- **SH write requires K-Means**: The `_write_sog_shN` function calls `rewrite_sh_by_kmeans` which clusters SH values into centroids.
- **WebP quality**: Pass through from callers (default 90).

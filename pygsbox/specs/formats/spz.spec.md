# spz — Niantic SPZ Format Reader/Writer

> Auto-generated code target: `formats/spz.py`

## 1. Purpose

Read/write SPZ format (Niantic Gaussian Splat), supporting versions v2, v3, v4.
- v2/v3: Single gzip-compressed blob with interleaved attributes
- v4: 32-byte header + TOC + separate zstd streams per attribute

## 2. Data Structures

### 2.1 SpzHeader

| Field | Type | Offset(v2/v3) | Offset(v4) | Purpose |
|-------|------|:---:|:---:|---------|
| magic | uint32 | 0 | 0 | 0x5053474E ("NGSP") |
| version | uint32 | 4 | 4 | 2, 3, or 4 |
| num_points | uint32 | 8 | 8 | Number of splats |
| sh_degree | uint8 | 12 | 12 | 0-3 |
| fractional_bits | uint8 | 13 | 13 | Always 12 |
| flags | uint8 | 14 | 14 | Reserved |
| num_streams | uint8 | — | 15 | Stream count (5 or 6) |
| toc_byte_offset | uint32 | — | 16 | TOC offset from file start |
| reserved | uint8 | 15 | 20 | 0 |
| size | | 16 bytes | 32 bytes | |

### 2.2 v2/v3 Data Layout (after header)

All attributes concatenated, then gzip-compressed:

| Segment | Bytes per splat | Total bytes | Encoding |
|---------|:---:|:---:|----------|
| Position X/Y/Z | 9 (3×3) | N×9 | 24-bit signed fixed point, scale=1/4096 |
| Alpha | 1 | N | Raw uint8 |
| Color R/G/B | 3 | N×3 | spz_encode_color |
| Scale X/Y/Z | 3 | N×3 | spz_encode_scale |
| Rotation (v2:3B, v3+:4B) | 3 or 4 | N×3 or N×4 | v2: 3-byte packed; v3+: 4-byte NQ |
| SH (optional) | 9/24/45 | N×SH | spz_encode_sh1/sh23 |

### 2.3 v4 Data Layout

32-byte header → TOC (num_streams × 16 bytes) → per-stream zstd-compressed data:

| Stream # | Content | Encoding |
|:---------:|---------|----------|
| 0 | Positions | N×9 bytes, zstd |
| 1 | Alphas | N bytes, zstd |
| 2 | Colors | N×3 bytes, zstd |
| 3 | Scales | N×3 bytes, zstd |
| 4 | Rotations | N×4 bytes, zstd |
| 5 (opt) | SH | N×SH bytes, zstd |

TOC entry: 8 bytes (zstd_size) + 8 bytes (uncompressed_size).

## 3. Public API

### 3.1 `read_spz(file_path: str) -> Tuple[SpzHeader, SplatData]`
- **Description**: Auto-detect v2/v3/v4 and read.
- **Detection**: Read first 4 bytes. If magic=0x5053474E, check version. If v4 → v4 path. If magic not found → assume gzip-compressed (v2/v3).
- **Algorithm**: See Section 4.

### 3.2 `write_spz(file_path: str, data: SplatData, sh_degree: int = 0, version: int = 4) -> None`
- **Description**: Write SPZ with specified version. v4 is default.

## 4. Algorithm

### 4.1 v2/v3 Reader

```
1. Decompress entire file with gzip
2. Parse header (first 16 bytes)
3. Calculate offsets:
   pos_size=N*9, alpha_size=N, color_size=N*3, scale_size=N*3
   rot_size=N*3(v2) or N*4(v3)
   sh_dim=0|N*9|N*24|N*45 (per sh_degree)
4. Validate: len(data) == N*(19|20)+sh_dim
5. For each splat i:
   - Decode 3 bytes from position block at i*3 offset per axis
   - Decode alpha, color, scale, rotation bytes
   - Copy SH bytes if sh_degree > 0
6. Return (header, SplatData)
```

### 4.2 v4 Reader

```
1. Parse header (first 32 bytes)
2. Seek to toc_byte_offset, read TOC
3. Read each stream size from TOC (8 bytes zstd, 8 raw)
4. zstd-decompress each stream in order
5. For each splat i, decode as v2/v3 but from separate decoded arrays
```

### 4.3 Writer (v3)

```
1. Build SpzHeader
2. Encode positions: spz_encode_position for each splat
3. Encode alphas, colors, scales, rotations in order
4. Encode SH if sh_degree > 0
5. Concatenate all bytes
6. gzip-compress
7. Write to file
```

### 4.4 Writer (v4)

```
1. Build SpzHeader with toc_byte_offset=32
2. Build separate byte arrays for positions, alphas, colors, scales, rotations, (SH)
3. zstd-compress each array
4. Build TOC: for each stream, 8B(zstd) + 8B(raw)
5. Write: header + TOC + concatenated zstd streams
```

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| File too small | `ValueError("File too small")` |
| Invalid magic | `ValueError("Invalid SPZ magic: {hex}")` |
| Unsupported fractional_bits | `ValueError("Unsupported FractionalBits: {n}")` |
| sh_degree > 3 | `ValueError("Unsupported SH degree: {n}")` |
| Data size mismatch | `ValueError("Invalid SPZ data size")` |
| v2 rotation (3-byte) | 4th component reconstructed via sqrt |
| Empty data (N=0) | Valid empty SPZ |
| zstandard not installed (v4) | `ImportError` at write time |

## 6. Examples

### 6.1 Read SPZ

```python
from pygsbox.formats.spz import read_spz
header, data = read_spz("model.spz")
print(f"v{header.version}: {data.count} splats, SH={header.sh_degree}")
```

### 6.2 Roundtrip v4

```python
from pygsbox.formats.spz import write_spz, read_spz
data = SplatData(100); # ... fill data
write_spz("test.spz", data, sh_degree=1, version=4)
hdr, decoded = read_spz("test.spz")
assert decoded.count == 100 and hdr.version == 4
assert np.max(np.abs(data.position - decoded.position)) < 0.01
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.codec` | spz_decode_position, spz_decode_scale, spz_decode_color, spz_decode_rotations_v3v4, spz_decode_rotations |
| `pygsbox.common.compress` | decompress_gzip, decompress_zstd, compress_gzip, compress_zstd |
| `pygsbox.core.splat_data` | SplatData |
| struct | Pack/unpack header fields |

## 8. Agent Notes

- **v2/v3 detection**: Check if first 4 bytes after decompression = SPZ_MAGIC. If not decompressed yet, assume gzip and decompress first.
- **v4 TOC position**: `header.toc_byte_offset` is absolute from file start. Typically 32 for standard header.
- **SH encoding**: v2/v3 uses quantized SH (spz_encode_sh1 for bands 0-8, spz_encode_sh23 for bands 9-44). The reader just copies the bytes — they're already uint8.
- **Fractional bits**: Always 12. This is the only supported value.

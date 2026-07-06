# spx — SPX Format Reader/Writer

> Auto-generated code target: `formats/spx.py`

## 1. Purpose

Read/write SPX format (block-based, supports v1/v2/v3).  
Each version uses increasingly sophisticated block formats and compression.

| Version | Block Formats | Compression | Position Encoding |
|---------|--------------|-------------|-------------------|
| v1 | SPLAT20 | gzip only | 24-bit fixed point |
| v2 | SPLAT19, SPLAT190_WEBP, SPLAT10019, SPLAT10190_WEBP | gzip or xz | 24-bit fixed point, optional log |
| v3 | SPLAT22, SPLAT23, SPLAT220_WEBP, SPLAT230_WEBP | gzip or xz | 24-bit fixed point, optional log |

## 2. Data Structures

### 2.1 SpxHeader (128 bytes)

| Offset | Type | Field | Notes |
|:------:|------|-------|-------|
| 0 | char[3] | fixed | "spx" |
| 3 | uint8 | version | 1, 2, or 3 |
| 4 | int32 | splat_count | |
| 8-32 | float32×6 | min_x, max_x, min_y, max_y, min_z, max_z | BBox |
| 32-40 | float32×2 | min_top_y, max_top_y | Top zone for scene orientation |
| 40 | uint32 | create_date | YYYYMMDD |
| 44 | uint32 | creater_id | 1202056903 (open format) |
| 48 | uint32 | exclusive_id | 0 (open format) |
| 52 | uint8 | sh_degree | 0-3 |
| 53 | uint8 | flags (v2+) | bit7: inverted |
| 54 | uint8 | lod (v2+) | LOD level |
| 55 | uint8 | reserve3 (v2+) | |
| 56-63 | uint32×2 | reserve1, reserve2 | 0 |
| 64-123 | char[60] | comment | UTF-8, null-padded |
| 124 | uint32 | hash | Rolling hash of bytes 0-123 |

### 2.2 Block Header (4 bytes)

- **Uncompressed**: positive int32 = block data size
- **Compressed**: negative int32 = `-(compressType << 28 | size)`
  - compressType: 0=gzip, 1=xz

### 2.3 Block Payload (after decompression)

| Offset | Type | Content |
|:------:|------|---------|
| 0 | uint32 | splat count in this block |
| 4 | uint32 | block format ID |
| 8+ | bytes | encoded data (format-dependent) |

## 3. Block Format IDs and Details

### 3.1 v1 Formats

#### BF_SPLAT20 (20)
20 bytes/splat, channel-interleaved: X(3B), Y(3B), Z(3B), scale(1B×3), color(1B×4), rotation(1B×4, normalized).

#### BF_SH1/SH2/SH3 (1/2/3)
SH coefficient blocks: 9B/24B/21B per splat (uint8, SH bands 1/1-2/3 only).

### 3.2 v2 Formats

#### BF_SPLAT19 (19)
19 bytes/splat, byte-plane interleaved for better compression.
Positions stored as byte0-byte1-byte2 grouped across axes and splats.
Rotation: only X,Y,Z stored (3 bytes/splat), W derived via `decode_spx_rotations`.

#### BF_SPLAT10019 (10019)
Same as SPLAT19 but positions are log-encoded. Header includes 4-byte `log_times` prefix.

#### BF_SPLAT190_WEBP (190)
4 separate WebP images: positions (3 RGB channels), scales, colors, rotations. Each prefixed with 4-byte size header.

#### BF_SPLAT10190_WEBP (10190)
Same as 190 but positions are log-encoded. Includes 12-byte prefix (8 block header + 4 log_times).

### 3.3 v3 Formats

#### BF_SPLAT22 (22) / BF_SPLAT23 (23)
22/23 bytes/splat. Includes palette_idx (2B) and flag_value (2B) fields.  
**SPLAT22**: with log encoding (log_times=1). **SPLAT23**: without log encoding.

#### BF_SPLAT220_WEBP (220) / BF_SPLAT230_WEBP (230)
8-channel WebP format: pos×3, scale, color, rotation(SOG encoded), palette, flag.

### 3.4 SH Formats

#### BF_SH_PALETTES (8) / BF_SH_PALETTES_WEBP (9)
Palette-based SH: centroids (60 bytes each for 15 bands) + per-splat palette_idx lookup.
v3 only.

#### BF_SH3_WEBP (4)
15-band SH stored as RGBA pixels in WebP. v2 only.

## 4. Public API

### 4.1 `read_spx(file_path: str) -> Tuple[SpxHeader, SplatData]`
- **Description**: Dispatch to v1/v2/v3 reader based on header version.

### 4.2 `write_spx(file_path, data, comment="", sh_degree=0, block_size=102400, block_format=220, quality=90, version=3) -> None`
- **Description**: Write with specified version and block format.

## 5. Algorithm (v3 Reader, most complex)

```
1. Parse 128-byte header
2. Loop: read 4-byte block header
   - If negative: extract compress_type + compressed_size → decompress
   - If positive: read raw
3. Parse block info: count(4B) + format_id(4B)
4. Dispatch by format_id:
   - SPLAT22/23 → decode_channels → decode_splat (with/without decode_log)
   - 220/230 → decode_webp_channels (8 WebP images) → decode_splat
   - SH_PALETTES → collect
5. If palettes collected: set_sh_by_palettes
6. Return (header, SplatData)
```

## 6. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Invalid magic | ValueError |
| Unsupported version | ValueError |
| Block format not recognized | ValueError |
| SH degree invalid (not 0-3) | Set to 0 |
| v1 reader encounters v2 block | ValueError (unknown format) |

## 7. Examples

```python
from pygsbox.formats.spx import read_spx, write_spx, BF_SPLAT220_WEBP

# Write v3 with WebP blocks
write_spx("model.spx", data, version=3, block_format=BF_SPLAT220_WEBP, quality=90)

# Read
hdr, data = read_spx("model.spx")
assert hdr.version == 3
```

## 8. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.common.codec` | decode_spx_position_uint24, decode_spx_scale, decode_log, sog_decode_rotations |
| `pygsbox.common.compress` | gzip, xz, WebP |
| struct, numpy | Binary parsing, array ops |

## 9. Agent Notes

- **SPLAT22 vs SPLAT23**: Only differ in whether positions are log-encoded. Reader must apply `decode_log` for 22/220.
- **v3 WebP rotation**: Uses SOG encoding (not NQ or 3-byte). Unpack via `sog_decode_rotations`.
- **Palette SH**: Stored as flat RGBA bytes, 60 bytes per palette entry (15 bands × 4 bytes). Unpacked R=palettes[idx], G=palettes[idx+1] XOR'd for anti-tamper.

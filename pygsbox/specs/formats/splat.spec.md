# splat — Raw Splat Format Reader/Writer

> Auto-generated code target: `formats/splat.py`

## 1. Purpose

Read/write raw `.splat` format — 32 bytes per splat, no header, no SH support.

## 2. Data Layout (32 bytes)

| Offset | Size | Type | Content |
|:------:|:---:|------|---------|
| 0 | 12 | float32×3 | Position (X, Y, Z) |
| 12 | 12 | float32×3 | Scale (linear, not log-space) |
| 24 | 4 | uint8×4 | Color (R, G, B, A) |
| 28 | 4 | uint8×4 | Rotation (W, X, Y, Z) |

## 3. Public API

### `read_splat(file_path: str) -> SplatData`
- **Description**: Read raw bytes, validate size divisible by 32, decode.
- **Algorithm**: `np.frombuffer(data, dtype=np.float32).reshape(count, 8)` + byte array indexing.
- **Error Cases**: `ValueError` if `len(data) % 32 != 0`.

### `write_splat(file_path: str, data: SplatData) -> None`
- **Description**: Encode SplatData to 32-byte/splat raw bytes.

## 4. Examples

```python
from pygsbox.formats.splat import read_splat, write_splat

write_splat("output.splat", data)
decoded = read_splat("output.splat")
assert decoded.count == data.count
```

## 5. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.core.splat_data` | from_splat_format_bytes, to_splat_format_bytes |

## 6. Agent Notes

- **No header, no SH**: This is the simplest format. 32 bytes exactly.
- **Thin wrapper**: Just calls `from_splat_format_bytes`/`to_splat_format_bytes` from splat_data.

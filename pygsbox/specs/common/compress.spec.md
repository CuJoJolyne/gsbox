# compress — Compression Utilities

> Auto-generated code target: `common/compress.py`

## 1. Purpose

Thin wrappers around standard library and optional third-party compression codecs (gzip, xz, zstd, WebP, ZIP). All functions take/return bytes.

## 2. Data Structures

None. Pure functions operating on `bytes`.

## 3. Constants

| Name | Value | Purpose |
|------|-------|---------|
| `HAS_ZSTD` | True/False | Set at import time by `try/except ImportError` |
| `HAS_PILLOW_WEBP` | True/False | Set at import time by `try/except ImportError` |

## 4. Public API

### 4.1 Gzip

#### `compress_gzip(data: bytes) -> bytes`
- **Algorithm**: `gzip.compress(data, compresslevel=6)`

#### `decompress_gzip(data: bytes) -> bytes`
- **Algorithm**: `gzip.decompress(data)`

### 4.2 XZ

#### `compress_xz(data: bytes) -> bytes`
- **Algorithm**: `lzma.compress(data, format=lzma.FORMAT_XZ)`

#### `decompress_xz(data: bytes) -> bytes`
- **Algorithm**: `lzma.decompress(data)`

### 4.3 Zstd (optional: zstandard)

#### `compress_zstd(data: bytes, level: int = 22) -> bytes`
- **Preconditions**: `zstandard` must be installed
- **Error Cases**: `ImportError("pip install zstandard")` if not available
- **Algorithm**: `ZstdCompressor(level=level).compress(data)`

#### `decompress_zstd(data: bytes) -> bytes`
- **Preconditions**: `zstandard` must be installed
- **Algorithm**: `ZstdDecompressor().decompress(data, max_output_size=len(data)*100)`

### 4.4 WebP (optional: Pillow with WebP)

#### `compress_webp(data: bytes, width: int = 0, height: int = 0, quality: int = 90) -> bytes`
- **Description**: Encode RGBA byte buffer to WebP lossless.
- **Algorithm**:
  1. If width/height=0: `compute_width_height(len(data))`
  2. Pad data to `width * height * 4` bytes with `0xFF`
  3. `Image.frombuffer("RGBA", (w,h), data, "raw", "RGBA", 0, 1)`
  4. `img.save(buf, "WEBP", lossless=True, method=6, quality=quality)`

#### `decompress_webp(data: bytes) -> tuple`
- **Description**: Decode WebP to RGBA bytes.
- **Returns**: `(rgba_bytes, width, height)`
- **Algorithm**: `Image.open`, `.convert("RGBA")`, `.tobytes("raw", "RGBA")`

#### `compute_width_height(length: int) -> tuple`
- **Description**: Compute square-ish image dimensions for a given byte count.
- **Algorithm**: `w = ceil(sqrt(length) / 4) * 4`, `h = ceil(length / w / 4) * 4`

### 4.5 ZIP

#### `unzip_file(zip_path: str, extract_dir: str) -> None`
- **Algorithm**: `zipfile.ZipFile(zip_path).extractall(extract_dir)`

#### `zip_files(zip_path: str, files: list) -> None`
- **Algorithm**: `zipfile.ZipFile(zip_path, 'w', ZIP_DEFLATED)`, write each file by basename.

## 5. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `decompress_zstd` without zstandard | `ImportError` |
| `compress_webp` without Pillow | `ImportError` |
| `compress_webp` with width=0 | Auto-compute |
| padding needed for WebP dimensions | Pad with `\xff\xff\xff\xff` |

## 6. Examples

### 6.1 Gzip Roundtrip

```python
from pygsbox.common.compress import compress_gzip, decompress_gzip
original = b"hello world " * 100
assert decompress_gzip(compress_gzip(original)) == original
```

### 6.2 Auto Dimensions

```python
from pygsbox.common.compress import compute_width_height
w, h = compute_width_height(200)  # 200 / 4 = 50 RGBA pixels
assert w * h * 4 >= 200
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| gzip (stdlib) | Gzip compression |
| lzma (stdlib) | XZ compression |
| zstandard (optional) | Zstd compression |
| PIL (optional) | WebP codec |
| zipfile (stdlib) | ZIP archive |
| numpy | Dimension calculation, array padding |
| io (stdlib) | BytesIO for WebP encoding |

## 8. Agent Notes

- **Optional dependency pattern**: Define `HAS_XXX = True/False` at module top via `try/except ImportError`. All functions check this and raise `ImportError` with helpful message ("pip install xxx").
- **Zstd max_output_size**: Multiply by 100 as a safety margin; zstd typically compresses >2:1 so this never overflows.
- **WebP padding**: Must pad RGBA buffer to exact `width*height*4` before `Image.frombuffer` or Pillow raises.
- **compute_width_height**: Always returns multiples of 4 for width and height to align with RGBA pixel structure.

import gzip
import lzma
import struct
import io
import zipfile
import numpy as np
from typing import Optional

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

try:
    from PIL import Image
    import pillow_webp as _webp_encoder
    HAS_PILLOW_WEBP = True
except ImportError:
    try:
        from PIL import Image
        HAS_PILLOW_WEBP = True
    except ImportError:
        HAS_PILLOW_WEBP = False


def compress_gzip(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=6)


def decompress_gzip(data: bytes) -> bytes:
    return gzip.decompress(data)


def compress_xz(data: bytes) -> bytes:
    return lzma.compress(data, format=lzma.FORMAT_XZ)


def decompress_xz(data: bytes) -> bytes:
    return lzma.decompress(data)


def compress_zstd(data: bytes, level: int = 22) -> bytes:
    if not HAS_ZSTD:
        raise ImportError("zstandard package required: pip install zstandard")
    cctx = zstd.ZstdCompressor(level=level)
    return cctx.compress(data)


def decompress_zstd(data: bytes) -> bytes:
    if not HAS_ZSTD:
        raise ImportError("zstandard package required: pip install zstandard")
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data, max_output_size=len(data) * 100)


def compress_webp(data: bytes, width: int = 0, height: int = 0, quality: int = 90) -> bytes:
    if not HAS_PILLOW_WEBP:
        raise ImportError("Pillow with WebP support required: pip install Pillow")

    if width == 0 or height == 0:
        width, height = compute_width_height(len(data))

    needed = width * height * 4
    if len(data) < needed:
        padded = bytearray(data)
        pad_pixels = (needed - len(data)) // 4
        padded.extend(b'\xff\xff\xff\xff' * pad_pixels)
        remaining = needed - len(padded)
        if remaining > 0:
            padded.extend(b'\x00' * remaining)
        data = bytes(padded)

    img = Image.frombuffer("RGBA", (width, height), data, "raw", "RGBA", 0, 1)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", lossless=True, method=6, quality=quality)
    return buf.getvalue()


def decompress_webp(data: bytes) -> tuple:
    if not HAS_PILLOW_WEBP:
        raise ImportError("Pillow with WebP support required: pip install Pillow")

    buf = io.BytesIO(data)
    img = Image.open(buf)
    img = img.convert("RGBA")  # type: ignore[assignment]
    width, height = img.size
    rgba_data = img.tobytes("raw", "RGBA")
    return rgba_data, width, height


def compute_width_height(length: int) -> tuple:
    w = int(np.ceil(np.sqrt(length) / 4.0) * 4.0)
    h = int(np.ceil(length / w / 4.0) * 4.0)
    return w, h


def unzip_file(zip_path: str, extract_dir: str):
    import os
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)


def zip_files(zip_path: str, files: list):
    import os
    os.makedirs(os.path.dirname(zip_path) or '.', exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, os.path.basename(file_path))

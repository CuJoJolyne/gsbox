import numpy as np
from typing import Optional
from ..core.splat_data import SplatData, from_splat_format_bytes, to_splat_format_bytes


def read_splat(file_path: str) -> SplatData:
    """Read .splat format file."""
    with open(file_path, 'rb') as f:
        data = f.read()

    file_size = len(data)
    if file_size % 32 != 0:
        raise ValueError("Invalid splat format: file size not multiple of 32")

    count = file_size // 32
    return from_splat_format_bytes(data, count)


def write_splat(file_path: str, data: SplatData):
    """Write .splat format file."""
    result = to_splat_format_bytes(data)
    with open(file_path, 'wb') as f:
        f.write(result)

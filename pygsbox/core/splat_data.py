import numpy as np
from typing import Optional, Tuple
from ..common import codec


class SplatData:
    """Columnar storage for Gaussian splat data using NumPy arrays."""
    position: 'np.ndarray'
    scale: 'np.ndarray'
    color: 'np.ndarray'
    rotation: 'np.ndarray'
    sh: 'np.ndarray'
    is_watermark: 'np.ndarray'
    flag_value: 'np.ndarray'
    palette_idx: 'np.ndarray'
    lod: 'np.ndarray'
    count: int

    def __init__(self, count: int = 0) -> None:
        self.count = count
        if count > 0:
            self.position = np.zeros((count, 3), dtype=np.float32)
            self.scale = np.zeros((count, 3), dtype=np.float32)
            self.color = np.zeros((count, 4), dtype=np.uint8)
            self.rotation = np.zeros((count, 4), dtype=np.uint8)
            self.sh = np.zeros((count, 45), dtype=np.uint8)
            self.is_watermark = np.zeros(count, dtype=bool)
            self.flag_value = np.zeros(count, dtype=np.uint16)
            self.palette_idx = np.zeros(count, dtype=np.uint16)
            self.lod = np.zeros(count, dtype=np.uint16)
        else:
            self.position = np.zeros((0, 3), dtype=np.float32)
            self.scale = np.zeros((0, 3), dtype=np.float32)
            self.color = np.zeros((0, 4), dtype=np.uint8)
            self.rotation = np.zeros((0, 4), dtype=np.uint8)
            self.sh = np.zeros((0, 45), dtype=np.uint8)
            self.is_watermark = np.zeros(0, dtype=bool)
            self.flag_value = np.zeros(0, dtype=np.uint16)
            self.palette_idx = np.zeros(0, dtype=np.uint16)
            self.lod = np.zeros(0, dtype=np.uint16)

    def __len__(self) -> int:
        return self.count

    def append(self, other: 'SplatData'):
        """Append another SplatData to this one."""
        if other.count == 0:
            return
        if self.count == 0:
            self.count = other.count
            self.position = other.position.copy()
            self.scale = other.scale.copy()
            self.color = other.color.copy()
            self.rotation = other.rotation.copy()
            self.sh = other.sh.copy()
            self.is_watermark = other.is_watermark.copy()
            self.flag_value = other.flag_value.copy()
            self.palette_idx = other.palette_idx.copy()
            self.lod = other.lod.copy()
        else:
            self.position = np.vstack([self.position, other.position])
            self.scale = np.vstack([self.scale, other.scale])
            self.color = np.vstack([self.color, other.color])
            self.rotation = np.vstack([self.rotation, other.rotation])
            self.sh = np.vstack([self.sh, other.sh])
            self.is_watermark = np.concatenate([self.is_watermark, other.is_watermark])
            self.flag_value = np.concatenate([self.flag_value, other.flag_value])
            self.palette_idx = np.concatenate([self.palette_idx, other.palette_idx])
            self.lod = np.concatenate([self.lod, other.lod])
            self.count += other.count

    def filter_alpha(self, min_alpha: int) -> 'SplatData':
        """Filter by alpha (ColorA channel)."""
        if min_alpha <= 0:
            return self
        mask = self.color[:, 3] >= min_alpha
        return self.subset(mask)

    def subset(self, mask: np.ndarray) -> 'SplatData':
        """Create a subset using a boolean mask."""
        result = SplatData(0)
        result.count = int(np.sum(mask))
        result.position = self.position[mask]
        result.scale = self.scale[mask]
        result.color = self.color[mask]
        result.rotation = self.rotation[mask]
        result.sh = self.sh[mask]
        result.is_watermark = self.is_watermark[mask]
        result.flag_value = self.flag_value[mask]
        result.palette_idx = self.palette_idx[mask]
        result.lod = self.lod[mask]
        return result

    def compute_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Compute min and max bounds for position."""
        if self.count == 0:
            return np.zeros(3), np.zeros(3)
        min_pos = np.min(self.position, axis=0)
        max_pos = np.max(self.position, axis=0)
        return min_pos, max_pos

    def compute_center_radius(self) -> Tuple[np.ndarray, float]:
        """Compute center point and bounding sphere radius."""
        if self.count == 0:
            return np.zeros(3), 0.0
        min_pos, max_pos = self.compute_bounds()
        center = (min_pos + max_pos) / 2.0
        extent = (max_pos - min_pos) / 2.0
        radius = float(np.linalg.norm(extent))
        return center, radius


def from_splat_format_bytes(data: bytes, count: int) -> SplatData:
    """Decode splat format bytes (32 bytes per splat)."""
    splat = SplatData(count)
    if count == 0:
        return splat

    arr = np.frombuffer(data, dtype=np.uint8).reshape(count, 32)

    splat.position[:, 0] = np.frombuffer(arr[:, 0:4].tobytes(), dtype=np.float32)
    splat.position[:, 1] = np.frombuffer(arr[:, 4:8].tobytes(), dtype=np.float32)
    splat.position[:, 2] = np.frombuffer(arr[:, 8:12].tobytes(), dtype=np.float32)

    splat.scale[:, 0] = np.frombuffer(arr[:, 12:16].tobytes(), dtype=np.float32)
    splat.scale[:, 1] = np.frombuffer(arr[:, 16:20].tobytes(), dtype=np.float32)
    splat.scale[:, 2] = np.frombuffer(arr[:, 20:24].tobytes(), dtype=np.float32)

    with np.errstate(invalid='ignore'):
        with np.errstate(divide='ignore'):
            splat.scale[:, 0] = np.clip(np.log(splat.scale[:, 0]).astype(np.float32), -200.0, 200.0)
            splat.scale[:, 1] = np.clip(np.log(splat.scale[:, 1]).astype(np.float32), -200.0, 200.0)
            splat.scale[:, 2] = np.clip(np.log(splat.scale[:, 2]).astype(np.float32), -200.0, 200.0)

    splat.color[:, 0] = arr[:, 24]
    splat.color[:, 1] = arr[:, 25]
    splat.color[:, 2] = arr[:, 26]
    splat.color[:, 3] = arr[:, 27]

    splat.rotation[:, 0] = arr[:, 28]
    splat.rotation[:, 1] = arr[:, 29]
    splat.rotation[:, 2] = arr[:, 30]
    splat.rotation[:, 3] = arr[:, 31]

    return splat


def to_splat_format_bytes(splat: SplatData) -> bytes:
    """Encode to splat format bytes (32 bytes per splat)."""
    result = bytearray(splat.count * 32)
    arr = np.frombuffer(result, dtype=np.float32).reshape(splat.count, 8)

    arr[:, 0] = splat.position[:, 0]
    arr[:, 1] = splat.position[:, 1]
    arr[:, 2] = splat.position[:, 2]

    with np.errstate(over='ignore'):
        arr[:, 3] = np.clip(np.exp(splat.scale[:, 0]).astype(np.float32), -3.4e38, 3.4e38)
        arr[:, 4] = np.clip(np.exp(splat.scale[:, 1]).astype(np.float32), -3.4e38, 3.4e38)
        arr[:, 5] = np.clip(np.exp(splat.scale[:, 2]).astype(np.float32), -3.4e38, 3.4e38)

    byte_arr = np.frombuffer(result, dtype=np.uint8).reshape(splat.count, 32)
    byte_arr[:, 24] = splat.color[:, 0]
    byte_arr[:, 25] = splat.color[:, 1]
    byte_arr[:, 26] = splat.color[:, 2]
    byte_arr[:, 27] = splat.color[:, 3]

    byte_arr[:, 28] = splat.rotation[:, 0]
    byte_arr[:, 29] = splat.rotation[:, 1]
    byte_arr[:, 30] = splat.rotation[:, 2]
    byte_arr[:, 31] = splat.rotation[:, 3]

    return bytes(result)

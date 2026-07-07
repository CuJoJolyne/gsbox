import numpy as np
from typing import Tuple
from . import splat_data


class V3MinMax:
    def __init__(self):
        self.min_x = 0.0
        self.min_y = 0.0
        self.min_z = 0.0
        self.max_x = 0.0
        self.max_y = 0.0
        self.max_z = 0.0
        self.len_x = 0.0
        self.len_y = 0.0
        self.len_z = 0.0
        self.center_x = 0.0
        self.center_y = 0.0
        self.center_z = 0.0
        self.radius = 0.0


def compute_xyz_min_max(data: splat_data.SplatData) -> V3MinMax:
    """Compute min/max bounds for position coordinates."""
    result = V3MinMax()
    if data.count == 0:
        return result

    result.min_x = float(np.min(data.position[:, 0]))
    result.min_y = float(np.min(data.position[:, 1]))
    result.min_z = float(np.min(data.position[:, 2]))
    result.max_x = float(np.max(data.position[:, 0]))
    result.max_y = float(np.max(data.position[:, 1]))
    result.max_z = float(np.max(data.position[:, 2]))

    result.len_x = result.max_x - result.min_x
    result.len_y = result.max_y - result.min_y
    result.len_z = result.max_z - result.min_z

    result.center_x = (result.max_x + result.min_x) / 2.0
    result.center_y = (result.max_y + result.min_y) / 2.0
    result.center_z = (result.max_z + result.min_z) / 2.0

    half_x = result.len_x * 0.5
    half_y = result.len_y * 0.5
    half_z = result.len_z * 0.5
    result.radius = float(np.sqrt(half_x ** 2 + half_y ** 2 + half_z ** 2))

    return result


def compute_xyz_log_min_max(data: splat_data.SplatData) -> V3MinMax:
    result = V3MinMax()
    if data.count == 0:
        return result
    pos = data.position
    abs_pos = np.abs(pos)
    log_vals = np.log(abs_pos + 1.0)
    neg_mask = pos < 0
    log_vals = np.where(neg_mask, -log_vals, log_vals)
    result.min_x = float(np.min(log_vals[:, 0]))
    result.max_x = float(np.max(log_vals[:, 0]))
    result.min_y = float(np.min(log_vals[:, 1]))
    result.max_y = float(np.max(log_vals[:, 1]))
    result.min_z = float(np.min(log_vals[:, 2]))
    result.max_z = float(np.max(log_vals[:, 2]))
    result.len_x = result.max_x - result.min_x
    result.len_y = result.max_y - result.min_y
    result.len_z = result.max_z - result.min_z
    return result


def part1_by2(x: np.ndarray) -> np.ndarray:
    """Spread bits for Morton encoding."""
    x = x.astype(np.uint32) & 0x000003FF
    x = (x ^ (x << 16)) & 0xFF0000FF
    x = (x ^ (x << 8)) & 0x0300F00F
    x = (x ^ (x << 4)) & 0x030C30C3
    x = (x ^ (x << 2)) & 0x09249249
    return x


def encode_morton3(positions: np.ndarray, mm: V3MinMax) -> np.ndarray:
    """Encode 3D positions to Morton codes for spatial sorting."""
    x = positions[:, 0]
    y = positions[:, 1]
    z = positions[:, 2]

    ix = np.where(mm.len_x > 0,
                  np.minimum(1023, np.floor(1024.0 * np.maximum(0, x - mm.min_x) / mm.len_x).astype(np.uint32)),
                  0).astype(np.uint32)
    iy = np.where(mm.len_y > 0,
                  np.minimum(1023, np.floor(1024.0 * np.maximum(0, y - mm.min_y) / mm.len_y).astype(np.uint32)),
                  0).astype(np.uint32)
    iz = np.where(mm.len_z > 0,
                  np.minimum(1023, np.floor(1024.0 * np.maximum(0, z - mm.min_z) / mm.len_z).astype(np.uint32)),
                  0).astype(np.uint32)

    return (part1_by2(iz) << 2) + (part1_by2(iy) << 1) + part1_by2(ix)  # type: ignore[no-any-return]


def sort_morton(data: splat_data.SplatData):
    """Sort splat data by Morton code for better compression."""
    if data.count == 0:
        return

    mm = compute_xyz_min_max(data)
    morton_codes = encode_morton3(data.position, mm)
    indices = np.argsort(morton_codes)

    data.position = data.position[indices]
    data.scale = data.scale[indices]
    data.color = data.color[indices]
    data.rotation = data.rotation[indices]
    data.sh = data.sh[indices]
    data.is_watermark = data.is_watermark[indices]
    data.flag_value = data.flag_value[indices]
    data.palette_idx = data.palette_idx[indices]
    data.lod = data.lod[indices]

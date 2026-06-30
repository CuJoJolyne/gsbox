import math
import numpy as np
from typing import Tuple, Optional
from ..core.splat_data import SplatData
from ..common import codec

SH_DIMS = [0, 9, 24, 45]


def get_sh_for_kmeans(data: SplatData, quality: int = 9) -> np.ndarray:
    shs = data.sh.astype(np.uint8).copy()
    if quality <= 5:
        mask9 = shs[:, :9]
        shs[:, :9] = np.floor(((mask9.astype(np.int32) + 4) // 8) * 8).astype(np.uint8)
        mask_rest = shs[:, 9:]
        shs[:, 9:] = np.floor(((mask_rest.astype(np.int32) + 8) // 16) * 16).astype(np.uint8)
    return shs


def sh_to_float32(shs_uint8: np.ndarray) -> np.ndarray:
    return (shs_uint8.astype(np.float32) - 128.0) / 128.0


def sh_float32_to_uint8(shs_f32: np.ndarray) -> np.ndarray:
    vals = np.round(shs_f32 * 128.0 + 128.0)
    return np.clip(vals, 0, 255).astype(np.uint8)


def try_fast_clustering(data: SplatData, dim: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    if dim == 0:
        return None
    shs = data.sh.astype(np.uint8)
    keys, inverse, counts = np.unique(shs[:, :dim], axis=0, return_inverse=True, return_counts=True)
    if len(keys) > 65536:
        return None
    order = np.argsort(-counts)
    centroids_uint8 = keys[order]
    centroids = np.zeros((len(order), 45), dtype=np.uint8)
    centroids[:, :dim] = centroids_uint8
    centroids[:, dim:] = 128
    idx_map = np.empty(len(order), dtype=np.int32)
    idx_map[order] = np.arange(len(order), dtype=np.int32)
    labels = idx_map[inverse].astype(np.int32)
    return centroids, labels


def kmeans_sh(data: SplatData, sh_degree: int,
              iterations: int = 5, max_bbf_nodes: int = 16,
              quality: int = 9) -> Tuple[np.ndarray, np.ndarray, int]:
    dim = SH_DIMS[sh_degree]
    n = data.count

    if sh_degree == 0 or dim == 0:
        return np.zeros((1, 45), dtype=np.uint8), np.zeros(n, dtype=np.int32), 1

    fast = try_fast_clustering(data, dim)
    if fast is not None:
        centroids, labels = fast
        return centroids, labels, len(centroids)

    log2_ratio = math.log2(max(1, n / 1024.0))
    palette_size = int(min(64, max(1, 2 ** math.floor(log2_ratio))) * 1024)
    palette_size = min(palette_size, max(1, n))

    shs_uint8 = get_sh_for_kmeans(data, quality)
    shs_f32 = sh_to_float32(shs_uint8)[:, :dim]

    try:
        from scipy.spatial import cKDTree
        centroids_f32, labels = _kmeans_with_scipy(
            shs_f32, palette_size, iterations, max_bbf_nodes
        )
    except ImportError:
        centroids_f32, labels = _kmeans_basic(shs_f32, palette_size, iterations)

    centroids_uint8 = np.full((palette_size, 45), 128, dtype=np.uint8)
    centroids_uint8[:, :dim] = sh_float32_to_uint8(centroids_f32)
    return centroids_uint8, labels.astype(np.int32), palette_size


def _kmeans_with_scipy(shs_f32: np.ndarray, palette_size: int,
                       iterations: int, max_bbf_nodes: int) -> Tuple[np.ndarray, np.ndarray]:
    from scipy.spatial import cKDTree
    n = len(shs_f32)
    rng = np.random.default_rng(0)
    idx = rng.choice(n, size=min(palette_size, n), replace=False)
    centroids_f32 = shs_f32[idx].copy()
    labels = np.zeros(n, dtype=np.int32)
    used = np.zeros(n, dtype=bool)
    used[idx] = True
    for i, ci in enumerate(idx):
        centroids_f32[i] = shs_f32[ci]

    for _ in range(iterations):
        tree = cKDTree(centroids_f32)
        _, labels = tree.query(shs_f32, k=1)
        labels = labels.astype(np.int32)

        new_centroids = np.zeros_like(centroids_f32)
        counts = np.zeros(palette_size, dtype=np.int32)
        np.add.at(new_centroids, labels, shs_f32)
        np.add.at(counts, labels, 1)

        empty = counts == 0
        counts = np.maximum(counts, 1)
        new_centroids /= counts[:, None]

        if np.any(empty):
            empty_indices = np.where(empty)[0]
            replace_indices = rng.choice(n, size=len(empty_indices), replace=True)
            new_centroids[empty_indices] = shs_f32[replace_indices]

        centroids_f32 = new_centroids

    return centroids_f32, labels


def _kmeans_basic(shs_f32: np.ndarray, palette_size: int,
                  iterations: int) -> Tuple[np.ndarray, np.ndarray]:
    n = len(shs_f32)
    rng = np.random.default_rng(0)
    idx = rng.choice(n, size=min(palette_size, n), replace=False)
    centroids_f32 = shs_f32[idx].copy()
    labels = np.zeros(n, dtype=np.int32)

    for _ in range(iterations):
        diffs = shs_f32[:, None, :] - centroids_f32[None, :, :]
        dists = np.sum(diffs * diffs, axis=2)
        labels = np.argmin(dists, axis=1).astype(np.int32)

        new_centroids = np.zeros_like(centroids_f32)
        counts = np.zeros(palette_size, dtype=np.int32)
        np.add.at(new_centroids, labels, shs_f32)
        np.add.at(counts, labels, 1)
        empty = counts == 0
        counts = np.maximum(counts, 1)
        new_centroids /= counts[:, None]

        if np.any(empty):
            empty_indices = np.where(empty)[0]
            replace_indices = rng.choice(n, size=len(empty_indices), replace=True)
            new_centroids[empty_indices] = shs_f32[replace_indices]

        centroids_f32 = new_centroids

    return centroids_f32, labels


def rewrite_sh_by_kmeans(data: SplatData, sh_degree: int,
                         iterations: int = 5, quality: int = 9
                         ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], int]:
    if sh_degree == 0 or data.count == 0:
        return None, None, 0

    centroids, labels, palette_size = kmeans_sh(
        data, sh_degree, iterations=iterations, quality=quality
    )
    data.palette_idx = np.clip(labels.astype(np.uint16), 0, 65535)
    data.sh = centroids[labels]
    return centroids, labels, palette_size


def build_labels_image(labels: np.ndarray, data_count: int) -> np.ndarray:
    from ..common.compress import compute_width_height
    w, h = compute_width_height(data_count)
    pixel_cnt = w * h
    img = np.full((pixel_cnt * 4,), 255, dtype=np.uint8)
    last_idx = max(0, data_count - 1)
    clipped_labels = labels[:data_count].astype(np.int32)
    clipped_labels = np.clip(clipped_labels, 0, last_idx)
    img[:data_count * 4][0::4] = (clipped_labels & 0xFF).astype(np.uint8)
    img[:data_count * 4][1::4] = ((clipped_labels >> 8) & 0xFF).astype(np.uint8)
    img[:data_count * 4][2::4] = 0
    return img

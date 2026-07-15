import math
import numpy as np
from typing import Tuple, Optional
from ..core.splat_data import SplatData
from ..common import codec

SH_DIMS = [0, 9, 24, 45]


class _Rng:
    """K-Means RNG with .intn(n) interface (wraps numpy PCG64)."""
    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)

    def intn(self, n: int) -> int:
        return int(self._rng.integers(0, n))

WEBP_QUALITY_TABLE = [80, 84, 86, 88, 90, 92, 94, 96, 99]


def quality_to_webp_quality(quality: int) -> int:
    qidx = max(0, min(8, quality - 1))
    return WEBP_QUALITY_TABLE[qidx]


def get_sh_for_kmeans(data: SplatData, quality: int = 5) -> np.ndarray:
    shs = data.sh.astype(np.uint8).copy()
    if quality <= 5:
        mask9 = shs[:, :9]
        shs[:, :9] = np.floor(((mask9.astype(np.int32) + 4) // 8) * 8).astype(np.uint8)
        mask_rest = shs[:, 9:]
        shs[:, 9:] = np.floor(((mask_rest.astype(np.int32) + 8) // 16) * 16).astype(np.uint8)
    elif quality == 6:
        mask_rest = shs[:, 9:]
        shs[:, 9:] = np.floor(((mask_rest.astype(np.int32) + 8) // 16) * 16).astype(np.uint8)
    elif quality == 7:
        mask_band3 = shs[:, 24:]
        shs[:, 24:] = np.floor(((mask_band3.astype(np.int32) + 8) // 16) * 16).astype(np.uint8)
    return shs


def sh_to_float32(shs_uint8: np.ndarray) -> np.ndarray:
    return (shs_uint8.astype(np.float32) - 128.0) / 128.0


def sh_float32_to_uint8(shs_f32: np.ndarray) -> np.ndarray:
    vals = np.round(shs_f32 * 128.0 + 128.0)
    return np.clip(vals, 0, 255).astype(np.uint8)


def try_fast_clustering(data: SplatData, dim: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Fast dedup clustering via hashing. Matches Go's tryFastClustering exactly."""
    if dim == 0:
        return None
    shs = data.sh.astype(np.uint8)
    n = data.count

    # Use hash-based dedup (matches Go's hex.EncodeToString approach)
    freq: dict = {}
    sh_list = []
    for i in range(n):
        key = bytes(shs[i, :dim])
        if key in freq:
            freq[key] = (freq[key][0], freq[key][1] + 1)
        else:
            if len(freq) > 65536:
                return None  # too many unique, abort early
            sh_list.append(key)
            freq[key] = (len(sh_list) - 1, 1)

    if len(freq) > 65536:
        return None

    # Sort by frequency desc (match Go)
    items = sorted(freq.items(), key=lambda x: -x[1][1])
    palette_size = len(items)
    centroids = np.zeros((palette_size, 45), dtype=np.uint8)
    centroids[:, dim:] = 128
    idx_map = np.zeros(palette_size, dtype=np.int32)

    for new_idx, (key, (old_idx, count)) in enumerate(items):
        centroids[new_idx, :dim] = np.frombuffer(key, dtype=np.uint8)
        idx_map[old_idx] = new_idx

    labels = np.zeros(n, dtype=np.int32)
    for i in range(n):
        key = bytes(shs[i, :dim])
        labels[i] = idx_map[freq[key][0]]

    return centroids, labels


def kmeans_sh(data: SplatData, sh_degree: int,
              iterations: int = 10, max_bbf_nodes: int = 15,
              quality: int = 5) -> Tuple[np.ndarray, np.ndarray, int]:
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
    shs_f32 = sh_to_float32(shs_uint8)

    # 1. Random unique init (deterministic seed for reproducibility)
    rng = _Rng(42)

    centroids_f32 = np.zeros((palette_size, 45), dtype=np.float32)
    used = set()
    i = 0
    max_fail = max(palette_size // 20, 1000)
    fail_cnt = 0
    while i < palette_size:
        idx = rng.intn(n)
        if idx not in used or fail_cnt >= max_fail:
            used.add(idx)
            centroids_f32[i] = shs_f32[idx]
            i += 1
        else:
            fail_cnt += 1

    labels = np.zeros(n, dtype=np.int32)
    prev_labels = None

    from .kmeans_bbf import _build_kdtree, _bbf_assign, _bbf_assign_numba, _HAS_NUMBA
    from ..common.progress import Progress, PHASE_KMEANS

    actual_iters = 0
    for it in range(iterations):
        Progress.report(PHASE_KMEANS, it, iterations)
        actual_iters += 1

        # 2. Build KD-Tree + BBF assignment
        tree = _build_kdtree(centroids_f32)
        if _HAS_NUMBA:
            labels = _bbf_assign_numba(shs_f32, tree, dim, max_bbf_nodes)
        else:
            labels = _bbf_assign(shs_f32, tree, dim, max_bbf_nodes)

        # 3. Compute new centroids + handle empties (vectorized, O(n*dim) numpy)
        # np.bincount is C-level SIMD — replaces both single-threaded Numba JIT
        # and pure-Python fallback loops (17M*45 iterations).
        counts = np.bincount(labels, minlength=palette_size).astype(np.int32)
        new_centroids = np.zeros((palette_size, 45), dtype=np.float32)
        for d in range(dim):
            new_centroids[:, d] = np.bincount(
                labels, weights=shs_f32[:, d], minlength=palette_size
            ).astype(np.float32)
        safe_counts = np.where(counts > 0, counts, 1).astype(np.float32)
        new_centroids[:, :dim] /= safe_counts[:, np.newaxis]

        # 4. Handle empty clusters: re-init from random data point (match Go)
        for c in range(palette_size):
            if counts[c] == 0:
                ridx = rng.intn(n)
                new_centroids[c] = shs_f32[ridx]

        centroids_f32 = new_centroids

        # 5. Early termination: stop if <0.1% of points changed assignment
        if prev_labels is not None:
            changed_frac = np.sum(labels != prev_labels) / n
            if changed_frac < 0.001:
                Progress.done(PHASE_KMEANS, actual_iters)
                break
        prev_labels = labels.copy()

    Progress.done(PHASE_KMEANS, actual_iters)

    # 4. Convert float32 → uint8, zero out dim..45
    centroids_uint8 = np.full((palette_size, 45), 128, dtype=np.uint8)
    centroids_uint8[:, :dim] = np.clip(np.round(centroids_f32[:, :dim] * 128.0 + 128.0), 0, 255).astype(np.uint8)

    # 5. Sort by descending count + remove empties (match Go's sortCentroidsByCounts)
    cnts = np.bincount(labels.astype(np.int32), minlength=palette_size)
    order = np.argsort(-cnts)
    valid_mask = cnts[order] > 0
    order = order[valid_mask]
    sorted_palette_size = len(order)
    orig_palette_size = palette_size
    if sorted_palette_size > 0 and sorted_palette_size < palette_size:
        sorted_centroids = np.full((sorted_palette_size, 45), 128, dtype=np.uint8)
        sorted_centroids[:, :dim] = centroids_uint8[order, :dim]
        centroids_uint8 = sorted_centroids
        palette_size = sorted_palette_size
        # reindex labels: map old centroid indices to sorted indices
        idx_map = np.full(orig_palette_size, -1, dtype=np.int32)
        idx_map[order] = np.arange(sorted_palette_size, dtype=np.int32)
        labels = idx_map[labels.astype(np.int32)]

    return centroids_uint8, labels.astype(np.int32), palette_size


def _kmeans_with_scipy(shs_f32: np.ndarray, palette_size: int,
                       iterations: int, max_bbf_nodes: int) -> Tuple[np.ndarray, np.ndarray]:
    from scipy.spatial import cKDTree
    n = len(shs_f32)
    rng = np.random.default_rng(1)
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
    rng = np.random.default_rng(1)
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
                         iterations: int = -1, quality: int = 5
                         ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], int]:
    if sh_degree == 0 or data.count == 0:
        return None, None, 0

    # Match Go's quality → KI/KN mapping (kis/kns arrays)
    _kis = [5, 7, 9, 10, 10, 10, 12, 15, 20]
    _kns = [10, 12, 14, 15, 15, 20, 30, 50, 100]
    qidx = max(0, min(8, quality - 1))
    ki = iterations if iterations > 0 else _kis[qidx]
    kn = _kns[qidx]

    centroids, labels, palette_size = kmeans_sh(
        data, sh_degree, iterations=ki, max_bbf_nodes=kn, quality=quality
    )
    data.palette_idx = np.clip(labels.astype(np.uint16), 0, 65535)
    data.sh = centroids[labels]
    return centroids, labels, palette_size


def build_labels_image(labels: np.ndarray, data_count: int) -> np.ndarray:
    from ..common.compress import compute_width_height
    w, h = compute_width_height(data_count)
    pixel_cnt = w * h
    img = np.zeros(pixel_cnt * 4, dtype=np.uint8)
    last_idx = max(0, data_count - 1)
    clipped_labels = labels[:data_count].astype(np.int32)
    clipped_labels = np.clip(clipped_labels, 0, last_idx)
    img[:data_count * 4][0::4] = (clipped_labels & 0xFF).astype(np.uint8)
    img[:data_count * 4][1::4] = ((clipped_labels >> 8) & 0xFF).astype(np.uint8)
    img[:data_count * 4][3::4] = 255
    return img

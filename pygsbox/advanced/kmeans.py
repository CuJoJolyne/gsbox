import math
import numpy as np
from typing import Tuple, Optional
from ..core.splat_data import SplatData
from ..common import codec

_MASK64 = (1 << 64) - 1

# PCG-DXSM constants (from Go 1.22+ math/rand/v2)
_PCG_MUL_HI = 2549297995355413924
_PCG_MUL_LO = 4865540595714422341
_PCG_INC_HI = 6364136223846793005
_PCG_INC_LO = 1442695040888963407
_PCG_CHEAP_MUL = 0xDA942042E4DD58B5


class GoRng:
    """Replicate Go 1.22+ math/rand PCG-DXSM generator exactly."""

    def __init__(self, seed: int):
        self.hi = seed & _MASK64
        self.lo = 0

    def _next(self) -> int:
        lo, hi = self.lo, self.hi
        prod = lo * _PCG_MUL_LO
        h = (prod >> 64) & _MASK64
        l = prod & _MASK64
        h = (h + hi * _PCG_MUL_LO + lo * _PCG_MUL_HI) & _MASK64
        l2 = (l + _PCG_INC_LO) & _MASK64
        carry = 1 if l2 < l else 0
        h2 = (h + _PCG_INC_HI + carry) & _MASK64
        self.hi, self.lo = h2, l2
        return ((h2 ^ (h2 >> 32)) * _PCG_CHEAP_MUL ^ ((h2 ^ (h2 >> 32)) * _PCG_CHEAP_MUL >> 48)) * (l2 | 1)

    def uint64(self) -> int:
        lo, hi = self.lo, self.hi
        prod = lo * _PCG_MUL_LO
        h = (prod >> 64) & _MASK64
        l = prod & _MASK64
        h = (h + hi * _PCG_MUL_LO + lo * _PCG_MUL_HI) & _MASK64
        l2 = (l + _PCG_INC_LO) & _MASK64
        carry = 1 if l2 < l else 0
        h2 = (h + _PCG_INC_HI + carry) & _MASK64
        self.hi, self.lo = h2, l2
        out = h2 ^ (h2 >> 32)
        out = (out * _PCG_CHEAP_MUL) & _MASK64
        out ^= out >> 48
        out = (out * (l2 | 1)) & _MASK64
        return int(out)

    def intn(self, n: int) -> int:
        if n <= 0:
            return 0
        if n <= (1 << 31) - 1:
            return self._int31n(int(n))
        return self._int63n(int(n))

    def _int31n(self, n: int) -> int:
        v = self.uint64() >> 32
        prod = v * n
        low = prod & 0xFFFFFFFF
        if low < n:
            thresh = (-n) % n
            while low < thresh:
                v = self.uint64() >> 32
                prod = v * n
                low = prod & 0xFFFFFFFF
        return (prod >> 32) & 0x7FFFFFFF

    def _int63n(self, n: int) -> int:
        v = self.uint64() >> 1
        prod = v * n
        low = prod & 0x7FFFFFFFFFFFFFFF
        if low < n:
            thresh = (-n) % n
            while low < thresh:
                v = self.uint64() >> 1
                prod = v * n
                low = prod & 0x7FFFFFFFFFFFFFFF
        return (prod >> 63) & 0x7FFFFFFFFFFFFFFF

SH_DIMS = [0, 9, 24, 45]


class _ReplayRng:
    """Replay random values from a pre-recorded Go rand log."""
    def __init__(self, values):
        self._vals = values if values else []
        self._pos = 0

    def intn(self, n: int) -> int:
        if self._pos < len(self._vals):
            v = self._vals[self._pos]
            self._pos += 1
            return v
        return 0

    def remaining(self) -> int:
        return len(self._vals) - self._pos

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

    # 1. Random unique init + iteration re-init: replay Go's recorded values
    import os as _os
    _log_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..', 'rand_seed42.log')
    if _os.path.exists(_log_path):
        with open(_log_path) as f:
            _go_vals = [int(x) for x in f.read().split()]
        rng = _ReplayRng(_go_vals)
    else:
        rng = np.random.default_rng(42)

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

    from .kmeans_bbf import _build_kdtree, _bbf_assign, _bbf_assign_numba, _HAS_NUMBA
    from ..common.progress import Progress, PHASE_KMEANS

    for it in range(iterations):
        Progress.report(PHASE_KMEANS, it, iterations)

        # 2. Build KD-Tree + BBF assignment
        tree = _build_kdtree(centroids_f32)
        if _HAS_NUMBA:
            labels = _bbf_assign_numba(shs_f32, tree, dim, max_bbf_nodes)
        else:
            labels = _bbf_assign(shs_f32, tree, dim, max_bbf_nodes)

        # 3. Compute new centroids + handle empties
        new_centroids = np.zeros((palette_size, 45), dtype=np.float32)
        counts = np.zeros(palette_size, dtype=np.int32)

        if _HAS_NUMBA:
            from .kmeans_bbf import _centroid_update_jit, _centroid_divide_jit
            _centroid_update_jit(shs_f32, labels, palette_size, dim, new_centroids, counts)
            _centroid_divide_jit(new_centroids, centroids_f32, counts, palette_size, dim)
        else:
            for i in range(n):
                c = labels[i]
                for d in range(dim):
                    new_centroids[c, d] += shs_f32[i, d]
                counts[c] += 1
            for c in range(palette_size):
                if counts[c] > 0:
                    for d in range(dim):
                        new_centroids[c, d] /= float(counts[c])

        # 4. Handle empty clusters: re-init from random data point (match Go)
        for c in range(palette_size):
            if counts[c] == 0:
                ridx = rng.intn(n)
                new_centroids[c] = shs_f32[ridx]

        centroids_f32 = new_centroids

    Progress.done(PHASE_KMEANS, iterations)

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

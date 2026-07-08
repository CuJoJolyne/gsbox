import math
from dataclasses import dataclass
from typing import Tuple, Optional, List
import numpy as np

@dataclass
class _KdNode:
    idx: int
    axis: int
    left: Optional['_KdNode'] = None
    right: Optional['_KdNode'] = None


class _FlatKdTree:
    """KD-tree flattened into numpy arrays for shared-memory multiprocessing."""
    __slots__ = ('idx', 'axis', 'left', 'right', 'cents', 'dim')
    def __init__(self, idx: np.ndarray, axis: np.ndarray, left: np.ndarray,
                 right: np.ndarray, cents: np.ndarray, dim: int):
        self.idx = idx; self.axis = axis
        self.left = left; self.right = right
        self.cents = cents; self.dim = dim


class _KdTree:
    def __init__(self, cents: np.ndarray, root: Optional[_KdNode]):
        self.cents = cents
        self.root = root
        self._flat: Optional[_FlatKdTree] = None

    def flatten(self) -> _FlatKdTree:
        if self._flat is not None:
            return self._flat
        if self.root is None:
            self._flat = _FlatKdTree(np.array([], dtype=np.int32), np.array([], dtype=np.int32),
                                      np.array([], dtype=np.int32), np.array([], dtype=np.int32),
                                      self.cents, 0)
            return self._flat
        # BFS traversal with queue (no O(n) pop(0))
        queue: List[Optional[_KdNode]] = [self.root]
        head = 0
        idxs, axes, lefts, rights = [], [], [], []
        while head < len(queue):
            n = queue[head]
            head += 1
            if n is None:
                continue
            ci = len(idxs)
            idxs.append(n.idx); axes.append(n.axis)
            if n.left:
                queue.append(n.left)
                lefts.append(ci + 1)
            else:
                lefts.append(-1)
            if n.right:
                queue.append(n.right)
                rights.append(ci + 1)
            else:
                rights.append(-1)
        self._flat = _FlatKdTree(
            np.array(idxs, dtype=np.int32), np.array(axes, dtype=np.int32),
            np.array(lefts, dtype=np.int32), np.array(rights, dtype=np.int32),
            self.cents, self.cents.shape[1])
        return self._flat


def _build_kdtree(cents: np.ndarray) -> _KdTree:
    """Build KD-tree from float centroids. Matches Go's buildKDTree exactly."""
    k = len(cents)
    idxs = np.arange(k, dtype=np.int32)

    def build(indices: np.ndarray, depth: int) -> Optional[_KdNode]:
        if len(indices) == 0:
            return None
        axis = depth % 45
        vals = cents[indices, axis]
        order = np.argsort(vals)
        sorted_indices = indices[order]
        med = len(sorted_indices) // 2
        return _KdNode(
            idx=int(sorted_indices[med]),
            axis=axis,
            left=build(sorted_indices[:med], depth + 1),
            right=build(sorted_indices[med + 1:], depth + 1),
        )
    return _KdTree(cents, build(idxs, 0))


def _bfs_search_chunk(args) -> np.ndarray:
    """BBF search for a chunk of points (worker function for multiprocessing)."""
    points, flat, dim, max_bbf_nodes, start, end = args
    n_chunk = end - start
    labels = np.zeros(n_chunk, dtype=np.int32)
    cents = flat.cents
    idx_arr, axis_arr = flat.idx, flat.axis
    left_arr, right_arr = flat.left, flat.right
    counter = 0

    for local_i in range(n_chunk):
        i = start + local_i
        pt_full = points[i]
        pt = pt_full[:dim]  # pre-slice once per point
        best_idx = -1
        best_dist = float('inf')

        heap = []
        root_node = 0
        heap.append((0.0, counter, root_node))
        counter += 1
        heap_size = 1
        visited = 0

        while heap_size > 0 and visited < max_bbf_nodes:
            min_pos = 0; min_val = heap[0][0]
            for j in range(1, heap_size):
                if heap[j][0] < min_val:
                    min_val = heap[j][0]; min_pos = j
            _, _, node_idx = heap.pop(min_pos)
            heap_size -= 1
            visited += 1

            cidx = idx_arr[node_idx]
            delta = pt - cents[cidx, :dim]
            dist = float(np.dot(delta, delta))
            if dist < best_dist:
                best_dist = dist
                best_idx = cidx

            axis = axis_arr[node_idx]
            diff = float(pt_full[axis]) - float(cents[cidx, axis])
            first = left_arr[node_idx] if diff < 0 else right_arr[node_idx]
            second = right_arr[node_idx] if diff < 0 else left_arr[node_idx]
            if first >= 0:
                heap.append((0.0, counter, first))
                counter += 1; heap_size += 1
            if second >= 0:
                heap.append((diff * diff, counter, second))
                counter += 1; heap_size += 1

        labels[local_i] = best_idx if best_idx >= 0 else 0
    return labels


def _bbf_assign(points: np.ndarray, tree: _KdTree, dim: int,
                max_bbf_nodes: int, num_workers: int = 0) -> np.ndarray:
    """Parallel BBF assignment (matches Go's parAssignDim).
    Default num_workers=0: auto-detect CPU count.
    Uses shared memory for large arrays (avoids pickle overhead).
    """
    n = len(points)
    flat = tree.flatten()

    if num_workers <= 0:
        import os
        num_workers = min(os.cpu_count() or 4, 8)
    if num_workers <= 1 or n < 2000:
        return _bfs_search_chunk((points, flat, dim, max_bbf_nodes, 0, n))

    import multiprocessing as mp
    from multiprocessing import shared_memory

    chunk_size = max(1, (n + num_workers - 1) // num_workers)

    # Shared memory for ALL large arrays (zero-copy between processes)
    def _to_shm(arr: np.ndarray):
        shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
        np.copyto(np.ndarray(arr.shape, arr.dtype, buffer=shm.buf), arr)
        return shm

    pts_shm = _to_shm(points)
    cents_shm = _to_shm(flat.cents)
    idx_shm = _to_shm(flat.idx)
    axis_shm = _to_shm(flat.axis)
    left_shm = _to_shm(flat.left)
    right_shm = _to_shm(flat.right)
    labels_shm = shared_memory.SharedMemory(create=True, size=n * 4)

    procs = []
    for w in range(num_workers):
        start = w * chunk_size
        end = min(start + chunk_size, n)
        if start >= end:
            continue
        p = mp.Process(target=_bfs_worker_shm, args=(
            pts_shm.name, points.shape, points.dtype,
            cents_shm.name, flat.cents.shape, flat.cents.dtype,
            idx_shm.name, flat.idx.shape, flat.idx.dtype,
            axis_shm.name, flat.axis.shape, flat.axis.dtype,
            left_shm.name, flat.left.shape, flat.left.dtype,
            right_shm.name, flat.right.shape, flat.right.dtype,
            labels_shm.name,
            dim, max_bbf_nodes, start, end))
        p.start()
        procs.append(p)

    for p in procs:
        p.join()

    result = np.ndarray((n,), dtype=np.int32, buffer=labels_shm.buf).copy()
    for s in [pts_shm, cents_shm, idx_shm, axis_shm, left_shm, right_shm, labels_shm]:
        s.close(); s.unlink()
    return result


def _bfs_worker_shm(pts_name, pts_shape, pts_dtype,
                    cents_name, cents_shape, cents_dtype,
                    idx_name, idx_shape, idx_dtype,
                    axis_name, axis_shape, axis_dtype,
                    left_name, left_shape, left_dtype,
                    right_name, right_shape, right_dtype,
                    labels_name,
                    dim, max_bbf_nodes, start, end):
    """Worker reading ALL data from shared memory (no pickle overhead)."""
    from multiprocessing import shared_memory
    pts = np.ndarray(pts_shape, pts_dtype, buffer=shared_memory.SharedMemory(name=pts_name).buf)
    cents = np.ndarray(cents_shape, cents_dtype, buffer=shared_memory.SharedMemory(name=cents_name).buf)
    idx_arr = np.ndarray(idx_shape, idx_dtype, buffer=shared_memory.SharedMemory(name=idx_name).buf)
    axis_arr = np.ndarray(axis_shape, axis_dtype, buffer=shared_memory.SharedMemory(name=axis_name).buf)
    left_arr = np.ndarray(left_shape, left_dtype, buffer=shared_memory.SharedMemory(name=left_name).buf)
    right_arr = np.ndarray(right_shape, right_dtype, buffer=shared_memory.SharedMemory(name=right_name).buf)
    labels = np.ndarray((pts_shape[0],), dtype=np.int32, buffer=shared_memory.SharedMemory(name=labels_name).buf)
    counter = 0

    for i in range(start, end):
        pt_full = pts[i]
        pt = pt_full[:dim]
        best_idx = -1; best_dist = float('inf')
        heap = [(0.0, counter, 0)]; counter += 1; heap_size = 1; visited = 0

        while heap_size > 0 and visited < max_bbf_nodes:
            min_pos = 0; min_val = heap[0][0]
            for j in range(1, heap_size):
                if heap[j][0] < min_val:
                    min_val = heap[j][0]; min_pos = j
            _, _, node_idx = heap.pop(min_pos)
            heap_size -= 1; visited += 1

            cidx = idx_arr[node_idx]
            delta = pt - cents[cidx, :dim]
            dist = float(np.dot(delta, delta))
            if dist < best_dist:
                best_dist = dist; best_idx = cidx

            axis = axis_arr[node_idx]
            diff = float(pt_full[axis]) - float(cents[cidx, axis])
            first = left_arr[node_idx] if diff < 0 else right_arr[node_idx]
            second = right_arr[node_idx] if diff < 0 else left_arr[node_idx]
            if first >= 0:
                heap.append((0.0, counter, first)); counter += 1; heap_size += 1
            if second >= 0:
                heap.append((diff * diff, counter, second)); counter += 1; heap_size += 1

        labels[i] = best_idx if best_idx >= 0 else 0

# ---- Numba JIT BBF (fast path) ----

try:
    import numba
    @numba.njit(cache=False, parallel=False, fastmath=True)
    def _bfs_jit(points, cents, idx_arr, axis_arr, left_arr, right_arr, dim, max_bbf_nodes, labels):
        n = len(points)
        for i in range(n):
            pt_full = points[i]
            pt = pt_full[:dim]
            best_idx = -1
            best_dist = np.inf
            heap_d = np.zeros(200, dtype=np.float64)
            heap_n = np.zeros(200, dtype=np.int32)
            heap_d[0] = 0.0; heap_n[0] = 0; heap_sz = 1; visited = 0
            while heap_sz > 0 and visited < max_bbf_nodes:
                mp = 0; mv = heap_d[0]
                for j in range(1, heap_sz):
                    if heap_d[j] < mv: mv = heap_d[j]; mp = j
                ni = heap_n[mp]; heap_sz -= 1
                if mp < heap_sz: heap_d[mp] = heap_d[heap_sz]; heap_n[mp] = heap_n[heap_sz]
                visited += 1
                cidx = idx_arr[ni]
                dist = 0.0
                for d in range(dim): delta = pt[d] - cents[cidx, d]; dist += delta * delta
                if dist < best_dist: best_dist = dist; best_idx = cidx
                ax = axis_arr[ni]
                diff = pt_full[ax] - cents[cidx, ax]
                f, s = (left_arr[ni], right_arr[ni]) if diff < 0.0 else (right_arr[ni], left_arr[ni])
                if f >= 0: heap_d[heap_sz] = 0.0; heap_n[heap_sz] = f; heap_sz += 1
                if s >= 0: heap_d[heap_sz] = diff * diff; heap_n[heap_sz] = s; heap_sz += 1
            labels[i] = best_idx if best_idx >= 0 else 0
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False


def _bbf_assign_numba(points, tree, dim, max_bbf_nodes):
    if not _HAS_NUMBA:
        return _bfs_search_chunk((points, tree.flatten(), dim, max_bbf_nodes, 0, len(points)))
    flat = tree.flatten(); n = len(points)
    labels = np.zeros(n, dtype=np.int32)
    pts = points.astype(np.float64, copy=False) if points.dtype == np.float64 else points.astype(np.float64)
    cts = flat.cents.astype(np.float64, copy=False) if flat.cents.dtype == np.float64 else flat.cents.astype(np.float64)
    _bfs_jit(pts, cts, flat.idx, flat.axis, flat.left, flat.right, dim, max_bbf_nodes, labels)
    return labels

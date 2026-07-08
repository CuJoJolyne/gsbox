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
    """Parallel BBF assignment via multiprocessing (matches Go's parAssignDim).
    On platforms where multiprocessing is unavailable (e.g. Windows python -c),
    falls back to single-threaded silently.
    """
    n = len(points)
    flat = tree.flatten()

    if num_workers > 1 and n >= 1000:
        import multiprocessing as mp
        chunk_size = max(1, (n + num_workers - 1) // num_workers)
        tasks = [(points, flat, dim, max_bbf_nodes, w * chunk_size, min((w + 1) * chunk_size, n))
                 for w in range(num_workers) if w * chunk_size < n]
        try:
            with mp.Pool(processes=len(tasks)) as pool:
                results = pool.map(_bfs_search_chunk, tasks)
            return np.concatenate(results)
        except (OSError, RuntimeError, mp.ProcessError):
            pass  # fallback to single-threaded

    return _bfs_search_chunk((points, flat, dim, max_bbf_nodes, 0, n))

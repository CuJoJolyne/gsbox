import heapq
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


class _KdTree:
    def __init__(self, cents: np.ndarray, root: Optional[_KdNode]):
        self.cents = cents
        self.root = root


def _build_kdtree(cents: np.ndarray) -> _KdTree:
    """Build KD-tree from float32 centroids. Matches Go's buildKDTree exactly."""
    k = len(cents)
    idxs = np.arange(k, dtype=np.int32)
    
    def build(indices: np.ndarray, depth: int) -> Optional[_KdNode]:
        if len(indices) == 0:
            return None
        axis = depth % 45
        # Sort indices by centroid values on current axis
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


_counter = 0

def _bbf_assign(points: np.ndarray, tree: _KdTree, dim: int,
                max_bbf_nodes: int) -> np.ndarray:
    """Assign each point to nearest centroid using BBF search.
    Matches Go's NearestBBF + parAssignDim algorithm (single-threaded).
    Inner distance computation is vectorized for Python performance.
    """
    global _counter
    n = len(points)
    labels = np.zeros(n, dtype=np.int32)
    cents = tree.cents

    for i in range(n):
        pt_dim = points[i, :dim].astype(np.float64)
        best_idx = -1
        best_dist = float('inf')

        # Use list as heap (avoids per-point heapq.Push/Pop overhead)
        heap = [(0.0, _counter, tree.root)] if tree.root is not None else []
        _counter += 1
        visited = 0

        while heap and visited < max_bbf_nodes:
            # Pop min-distance node
            min_pos = 0
            for j in range(1, len(heap)):
                if heap[j][0] < heap[min_pos][0]:
                    min_pos = j
            _, _, node = heap.pop(min_pos)
            visited += 1

            cent_dim = cents[node.idx, :dim].astype(np.float64)
            dist = float(np.sum((pt_dim - cent_dim) ** 2))
            if dist < best_dist:
                best_dist = dist
                best_idx = node.idx

            axis = node.axis
            diff = float(float(points[i, axis]) - float(cents[node.idx, axis]))
            first = node.left if diff < 0 else node.right
            second = node.right if diff < 0 else node.left
            if first is not None:
                heap.append((0.0, _counter, first))
                _counter += 1
            if second is not None:
                heap.append((diff * diff, _counter, second))
                _counter += 1

        labels[i] = best_idx if best_idx >= 0 else 0

    return labels

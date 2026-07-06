# simplify — Voxel-based Gaussian Simplification

> Auto-generated code target: `advanced/simplify.py`

## 1. Purpose

Reduce splat count by merging similar nearby Gaussians. Uses voxel-grid spatial hashing to find candidates, similarity scoring to select pairs, and covariance-aware 2-splat Gaussian merging.

## 2. Key Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `grid_size_factor` | 2.5 | Voxel size = avg_scale × factor |
| `merge_threshold` | -3.0 | Score threshold for merging |
| `block_size` | 128.0 | Spatial block size for parallel processing |
| `ALPHA_MIN` | 20 | Filter out low-alpha splats |

## 3. Public API

### `simplify(data: SplatData, grid_size_factor=2.5, merge_threshold=-3.0, block_size=128.0) -> SplatData`
- **Description**: Reduce splat count, return new SplatData.

## 4. Algorithm

```
1. Filter: keep splats with alpha >= 20
2. Compute importance: volume = exp(sx)*exp(sy)*exp(sz)*opacity
3. Sort by descending importance
4. Partition into spatial blocks (128×128×128 grid)
5. For each block, within each voxel cell:
   a. For each unmerged splat i:
      - Search 3×3×3 neighbor cells for candidate j
      - Skip if scale ratio out of [0.5, 3.0]
      - Compute similarity score: -(dist_sq + color_diff*0.5 + scale_diff/scale_sum*2.0)
      - If score > merge_threshold: merge i and j
6. Merge: weighted average of position, color; covariance decomposition for scale+rotation
7. Return merged + unmerged splats
```

## 5. Gaussian Merge Algorithm

```
1. pos = weighted average of positions (by importance)
2. color = weighted average of RGBA
3. Build covariance matrices from rotations and scales
4. Weighted sum of covariances + distance covariances
5. Eigenvalue decomposition → new scale (log(sqrt(eigenvalues)))
6. Eigenvectors → new rotation (matrix to quaternion)
```

## 6. Edge Cases

| Scenario | Behavior |
|----------|----------|
| All alphas < 20 | Return empty SplatData |
| Count < 2 | Return as-is |
| No merge candidates | Return original |
| Eigenvalue < 1e-9 | Clamp to 1e-9 |

## 7. Examples

```python
from pygsbox.advanced.simplify import simplify

reduced = simplify(data, grid_size_factor=3.0)
print(f"Simplified: {data.count} -> {reduced.count}")
```

## 8. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Matrix operations, eigen decomposition |
| `pygsbox.common.codec` | encode/decode rotation |

## 9. Agent Notes

- **Splat merging is the core**: The `_merge_two` function builds 3×3 covariance matrices from rotation and scale, sums them with distance covariances, then decomposes via `np.linalg.eigh`.
- **Quaternion from rotation matrix**: Use `mat_to_quat` which extracts trace-based conversion.
- **Similarity scoring**: Larger (more negative) score = more similar. Threshold of -3.0 is empirical.
- **Block partitioning**: Uses `block_map[tuple(int32×3)]` dict to group splats for parallel processing.

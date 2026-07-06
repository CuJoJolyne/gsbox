# kmeans — K-Means SH Clustering

> Auto-generated code target: `advanced/kmeans.py`

## 1. Purpose

Cluster spherical harmonics coefficients via K-Means across all splats, producing a shared codebook (palette) of centroids and per-splat palette indices. Reduces file size significantly when SH data is highly redundant.

## 2. Public API

### 2.1 `kmeans_sh(data, sh_degree, iterations=5, max_bbf_nodes=16, quality=9) -> Tuple[ndarray, ndarray, int]`
- **Description**: Run K-Means on SH data. Returns (centroids uint8[Npal,45], labels int32[N], palette_size).
- **Algorithm**:
  1. Compute `dim` from sh_degree: 0→0, 1→9, 2→24, 3→45
  2. Try fast dedup path: if unique SH[:dim] rows ≤ 65536, return them sorted by frequency
  3. Otherwise: compute palette_size = min(64, 2^floor(log2(N/1024))) * 1024
  4. Initialize centroids randomly, run iterations of:
     a. Build cKDTree (scipy) or brute-force nearest neighbor (numpy)
     b. Assign each point to nearest centroid
     c. Compute new centroids as means of assigned points
     d. Handle empty clusters by random re-initialization
  5. Return centroids, labels, palette_size

### 2.2 `rewrite_sh_by_kmeans(data, sh_degree, iterations=5, quality=9) -> Tuple[Optional[ndarray], Optional[ndarray], int]`
- **Description**: Cluster SH and rewrite data.sh to centroids, set data.palette_idx.
- **Returns**: (centroids, labels, palette_size)
- **Edge Cases**: sh_degree=0 or data.count=0 → return (None, None, 0)

### 2.3 `build_labels_image(labels: ndarray, data_count: int) -> ndarray`
- **Description**: Create WebP-compatible RGBA labels image for SOG output.
- **Algorithm**: Compute width/height from data_count, fill R=label&0xFF, G=label>>8, B=0, A=255.

## 3. Algorithm Details

### 3.1 Fast Dedup Path

```
1. np.unique(data.sh[:, :dim], axis=0, return_inverse=True, return_counts=True)
2. Sort by -count
3. If unique count > 65536: fall through to full K-Means
4. Create centroids array with dim...45 set to 128 (zero)
5. Remap indices via sorted order
```

### 3.2 Palette Size Formula

`palette_size = min(64, max(1, 2^floor(log2(N/1024)))) * 1024`

For N=5000: floor(log2(4.88))=2 → 2^2=4 → min(64,4)=4 → 4*1024=4096 (clamped to N)

### 3.3 KD-Tree Nearest Neighbor

```
1. cKDTree(centroids_f32)
2. _, labels = tree.query(shs_f32, k=1)
3. np.add.at(new_centroids, labels, shs_f32)
4. np.add.at(counts, labels, 1)
5. new_centroids /= counts
```

## 4. Edge Cases

| Scenario | Behavior |
|----------|----------|
| sh_degree=0 | Return early (palette_size=1) |
| dim=0 | No clustering needed |
| All SH values unique | Fast path returns all unique as centroids |
| scipy not installed | Fall back to brute-force numpy K-Means |
| Empty centroids cluster | Re-initialize with random data point |

## 5. Examples

```python
from pygsbox.advanced.kmeans import rewrite_sh_by_kmeans

centroids, labels, palette_size = rewrite_sh_by_kmeans(data, sh_degree=1, iterations=3)
assert data.sh is centroids[labels]  # data was rewritten
```

## 6. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Array operations, unique, bincount |
| scipy (optional) | cKDTree for fast nearest neighbor |
| `pygsbox.common.codec` | decode_splat_sh, encode_splat_sh |

## 7. Agent Notes

- **scipy optional**: Try `from scipy.spatial import cKDTree`; fall back to numpy brute-force if unavailable.
- **SH quality quantization**: Before clustering, SH values may be quantized per Go logic (spz_encode_sh1/sh23 based on quality level). This improves compression.
- **centroids[labels] must equal data.sh after rewrite**: This is a key invariant for roundtrip testing.

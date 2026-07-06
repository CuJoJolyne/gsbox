# lod — B-Tree LOD Spatial Partitioning

> Auto-generated code target: `advanced/lod.py`

## 1. Purpose

Build B-Tree spatial partitioning for Level-of-Detail (LOD) rendering. Split splats along the longest axis recursively until leaf nodes fit within `cut_size`.

## 2. Data Structures

### 2.1 BTreeNode
Internal representation of the B-Tree. Contains: SplatData, min/max bounds, lod_counts dict, TileMapping lods list, children list.

### 2.2 SplatTiles / LodMeta
Output structures. SplatTiles holds file-to-data mappings. LodMeta is the JSON-serializable lod-meta.json format.

## 3. Public API

### 3.1 `build_btree(data: SplatData, cut_size: int, lod_levels: int = 0) -> BTreeNode`
- **Description**: Build B-Tree recursively.
- **Algorithm**:
  1. Compute min/max bounds
  2. If count ≤ cut_size: mark as leaf, create TileMapping per lod
  3. Else: find longest axis, sort, split at median, recurse on children

### 3.2 `build_tiles_from_btree(data, root, lod_levels, sh_degree=0) -> Tuple[SplatTiles, LodMeta]`
- **Description**: Convert B-Tree to output format. Merge leaf nodes into SplatFiles per LOD level.

### 3.3 `lod_meta_to_json(meta: LodMeta) -> str`
### 3.4 `lod_meta_from_json(json_str: str) -> LodMeta`
- **Description**: JSON roundtrip for lod-meta.json.

## 4. Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `FILE_SPLAT_COUNT_THRESHOLD` | 409600 | Max splats per file before splitting |

## 5. Algorithm Detail

### 5.1 B-Tree Split

```
1. _calc_longest_axis(mm) → axis index (0=X, 1=Y, 2=Z)
2. Sort data by axis values
3. Split at median
4. Create left/right BTreeNodes with computed bounds
5. If child count ≤ cut_size: mark leaf + create TileMappings
```

### 5.2 Tile Merging

```
For each LOD level:
  Collect leaf nodes whose lod_counts[lod] ≤ threshold
  Merge their data into SplatFiles
  Record offset/count in TileMappings
```

## 6. Examples

```python
from pygsbox.advanced.lod import build_btree, build_tiles_from_btree, lod_meta_to_json

root = build_btree(data, cut_size=1000)
tiles, meta = build_tiles_from_btree(data, root, 1)
json_str = lod_meta_to_json(meta)
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| numpy | Array sorting, splitting |
| `pygsbox.core.morton` | V3MinMax, compute_xyz_min_max |

## 8. Agent Notes

- **cut_size controls leaf size**: Smaller values = more tiles = finer LOD granularity.
- **B-Tree is binary**: Each split creates exactly 2 children (median split). Not a traditional B+ tree.
- **LOD levels**: Each splat has a `lod` field (uint16) tagging its LOD level. The B-Tree tracks `lod_counts` per node.
- **SplatFile.datas is Optional**: May be None when file metadata is generated before data collection.

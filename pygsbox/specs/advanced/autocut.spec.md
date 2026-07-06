# autocut — Automatic LOD Pipeline

> Auto-generated code target: `advanced/autocut.py`

## 1. Purpose

One-stop pipeline: simplify x5 → merge into multi-level LOD → build B-Tree → write lod-meta.json.  
Equivalent of Go's `autocut` command.

## 2. Public API

### `autocut(data: SplatData, output_path: str, sh_degree: int = 0, lod_levels: int = 6, cut_size: int = 102400) -> str`
- **Description**: Run the full autocut pipeline. Returns path to lod-meta.json.

## 3. Pipeline Steps

```
1. LOD 0: original data (lod=0)
2. For level in 1..lod_levels-1:
   a. simplified = simplify(previous)
   b. simplified.lod = level
   c. Log count reduction percentage
3. Merge all LOD datasets into one
4. sort_morton(merged)
5. build_btree(merged, cut_size, lod_levels)
6. build_tiles_from_btree → SplatTiles + LodMeta
7. lod_meta_to_json(meta) → write to output_path
```

## 4. Output

- `lod-meta.json`: JSON file with lodLevels, filenames[], tree structure
- Side effect: prints LOD level summaries to stdout

## 5. Examples

```python
from pygsbox.advanced.autocut import autocut

autocut(data, "output/lod-meta.json", sh_degree=1)
# Output: LOD 0: 500000 points (original)
#         LOD 1: 350000 points (30.0% reduction)
#         ...
```

## 6. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.core.morton` | sort_morton |
| `pygsbox.advanced.simplify` | simplify |
| `pygsbox.advanced.lod` | build_btree, build_tiles_from_btree, lod_meta_to_json |

## 7. Agent Notes

- **lod_levels=6 by default**: LOD 0-5 (original + 5 simplify passes).
- **cut_size=102400**: Matches Go default. Tune for desired tile granularity.
- **Data is mutated in-place**: The simplify function creates new SplatData objects, but the initial data's lod field is set.
- **Output is a single JSON file**: Does not write SOG tiles (that's done by LOD meta writer, not implemented in Python).

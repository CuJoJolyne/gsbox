import os
import numpy as np
from typing import List
from ..core.splat_data import SplatData
from ..core.morton import sort_morton
from .simplify import simplify
from .lod import build_btree, build_tiles_from_btree, lod_meta_to_json


def autocut(data: SplatData, output_path: str, sh_degree: int = 0,
            lod_levels: int = 6, cut_size: int = 102400) -> str:
    """
    Auto-cut: simplify progressively, build LOD B-Tree, write lod-meta.json.
    Returns the path to the lod-meta.json file.
    """
    from ..formats.sog import write_sog
    from ..common.file_utils import write_file_string

    datas: List[SplatData] = []

    # LOD 0: original data
    data0 = data
    data0.lod = np.zeros(data0.count, dtype=np.uint16)
    datas.append(data0)
    print(f"[Info]   LOD 0: {data0.count} points (original)")

    # LOD 1-5: progressively simplified
    current = data
    for level in range(1, lod_levels):
        simplified = simplify(current)
        simplified.lod = np.full(simplified.count, level, dtype=np.uint16)
        reduction = (1 - simplified.count / current.count) * 100
        print(f"[Info]   LOD {level}: {simplified.count} points ({reduction:.1f}% reduction)")
        datas.append(simplified)
        current = simplified

    # Merge all LODs into single dataset
    merged = SplatData(0)
    for ds in datas:
        merged.append(ds)
    sort_morton(merged)

    print(f"[Info] Total merged: {merged.count} points, building B-Tree...")

    # Build B-Tree LOD tiles
    root = build_btree(merged, cut_size=cut_size, lod_levels=lod_levels)
    tiles, meta = build_tiles_from_btree(
        merged, root, lod_levels=lod_levels, sh_degree=sh_degree,
        magic="splat-lod", version=1,
    )

    # Write lod-meta.json
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    json_str = lod_meta_to_json(meta)
    write_file_string(output_path, json_str)

    print(f"[Info] LOD tiles: {len(tiles.files)} tiles, meta written to {output_path}")
    return output_path

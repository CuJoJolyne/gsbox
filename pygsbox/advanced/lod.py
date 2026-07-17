import math
import json
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from ..core.splat_data import SplatData
from ..core.morton import V3MinMax, compute_xyz_min_max, sort_morton, sort_morton

FILE_SPLAT_COUNT_THRESHOLD = 409600


@dataclass
class Bound:
    min: List[float]
    max: List[float]


@dataclass
class LodMapping:
    file: int
    offset: int
    count: int


@dataclass
class TileMapping:
    file_key: str
    offset: int
    count: int
    datas: Optional[SplatData] = None


@dataclass
class SplatFile:
    file_key: str
    index: int
    url: str
    lod: int
    seq: int
    count: int
    datas: Optional[SplatData] = None


@dataclass
class SplatNode:
    center: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    radius: float = 0.0
    children: Optional[List['SplatNode']] = None
    lods: Optional[List[TileMapping]] = None
    bound: Optional[Bound] = None


@dataclass
class LodNode:
    bound: Optional[Bound] = None
    children: Optional[List['LodNode']] = None
    lods: Optional[Dict[str, LodMapping]] = None


@dataclass
class LodMeta:
    lod_levels: int
    filenames: List[str]
    environment: str = ""
    tree: Optional[LodNode] = None


@dataclass
class SplatTiles:
    version: int
    magic: str
    lod_levels: int
    total_count: int
    files: Dict[str, SplatFile]
    tree: SplatNode
    sh_degree: int = 0
    comment: str = ""
    environment: str = ""


class BTreeNode:
    def __init__(self, mm: V3MinMax, data: Optional[SplatData] = None,
                 level: int = 1, cut_size: int = FILE_SPLAT_COUNT_THRESHOLD):
        self.data = data
        self.mm = mm
        self.level = level
        self.is_leaf = data.count <= cut_size if data is not None else False
        self.children: List['BTreeNode'] = []
        self.lod_counts: Dict[int, int] = {}
        self.lods: List[Optional[TileMapping]] = []
        self.bound: Optional[Bound] = None

        if data is not None:
            lod_vals = data.lod if data.lod.size > 0 else np.zeros(data.count, dtype=np.uint16)
            unique_lods, counts = np.unique(lod_vals, return_counts=True)
            self.lod_counts = dict(zip(unique_lods.astype(int).tolist(), counts.astype(int).tolist()))
            self.cut_size = cut_size
        else:
            self.cut_size = cut_size


def _calc_longest_axis(mm: V3MinMax) -> Tuple[float, float, int]:
    if mm.len_x >= mm.len_y and mm.len_x >= mm.len_z:
        return mm.min_x, mm.len_x, 0
    elif mm.len_y >= mm.len_x and mm.len_y >= mm.len_z:
        return mm.min_y, mm.len_y, 1
    return mm.min_z, mm.len_z, 2


def _split_axis(mm: V3MinMax, axis: int) -> Tuple[V3MinMax, V3MinMax]:
    mm0 = V3MinMax()
    mm1 = V3MinMax()
    for attr in ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z",
                 "len_x", "len_y", "len_z", "center_x", "center_y", "center_z",
                 "radius"):
        setattr(mm0, attr, getattr(mm, attr))
        setattr(mm1, attr, getattr(mm, attr))

    if axis == 0:
        split = mm.center_x
        mm0.max_x, mm0.len_x = split, split - mm.min_x
        mm0.center_x = (mm0.min_x + mm0.max_x) / 2.0
        mm1.min_x, mm1.len_x = split, mm.max_x - split
        mm1.center_x = (mm1.min_x + mm1.max_x) / 2.0
    elif axis == 1:
        split = mm.center_y
        mm0.max_y, mm0.len_y = split, split - mm.min_y
        mm0.center_y = (mm0.min_y + mm0.max_y) / 2.0
        mm1.min_y, mm1.len_y = split, mm.max_y - split
        mm1.center_y = (mm1.min_y + mm1.max_y) / 2.0
    else:
        split = mm.center_z
        mm0.max_z, mm0.len_z = split, split - mm.min_z
        mm0.center_z = (mm0.min_z + mm0.max_z) / 2.0
        mm1.min_z, mm1.len_z = split, mm.max_z - split
        mm1.center_z = (mm1.min_z + mm1.max_z) / 2.0

    return mm0, mm1


def build_btree(data: SplatData, cut_size: int, lod_levels: int = 0) -> BTreeNode:
    mm = compute_xyz_min_max(data)
    root = BTreeNode(mm=mm, data=data, level=1, cut_size=cut_size)

    if lod_levels <= 0:
        max_lod = int(np.max(data.lod)) if data.count > 0 and data.lod.size > 0 else 0
        lod_levels = max_lod + 1

    if data.count <= cut_size:
        root.is_leaf = True
        root.lods = [TileMapping("", 0, data.count, None) for _ in range(lod_levels)]
        return root

    queue = [root]
    while queue:
        node = queue.pop(0)
        if node.is_leaf or node.data is None:
            continue
        _split_btree_node(node, lod_levels)
        queue.extend(node.children)

    return root


def _split_btree_node(node: BTreeNode, lod_levels: int):
    if node.data is None or node.data.count < 2:
        node.is_leaf = True
        return

    _, _, axis = _calc_longest_axis(node.mm)
    positions = node.data.position
    axis_vals = positions[:, axis]
    order = np.argsort(axis_vals)
    mid = len(order) // 2

    left_idx = order[:mid]
    right_idx = order[mid:]

    mask_left = mask_to_bool_idx(node.data.count, left_idx)
    mask_right = mask_to_bool_idx(node.data.count, right_idx)

    left_data = node.data.subset(mask_left)
    right_data = node.data.subset(mask_right)

    mm_left = compute_xyz_min_max(left_data)
    mm_right = compute_xyz_min_max(right_data)

    node_left = BTreeNode(mm=mm_left, data=left_data, level=node.level + 1, cut_size=node.cut_size)
    node_right = BTreeNode(mm=mm_right, data=right_data, level=node.level + 1, cut_size=node.cut_size)

    node_left.is_leaf = left_data.count <= node.cut_size
    node_right.is_leaf = right_data.count <= node.cut_size

    if node_left.is_leaf:
        _split_leaf_by_lod(node_left, left_data, lod_levels)
    if node_right.is_leaf:
        _split_leaf_by_lod(node_right, right_data, lod_levels)

    node.children = [node_left, node_right]
    node.data = None


def _split_leaf_by_lod(node: BTreeNode, data: SplatData, lod_levels: int):
    """Split leaf data by LOD into separate TileMapping entries, matching Go."""
    node.lods = []
    for lod in range(lod_levels):
        count = node.lod_counts.get(lod, 0)
        if count > 0:
            mask = data.lod == lod
            lod_data = data.subset(mask)
            tm = TileMapping("", 0, count, lod_data)
            node.lods.append(tm)
        else:
            node.lods.append(None)


def mask_to_bool_idx(size: int, indices: np.ndarray) -> np.ndarray:
    mask = np.zeros(size, dtype=bool)
    mask[indices] = True
    return mask


def _traverse_tree(node: BTreeNode, callback) -> None:
    if not callback(node):
        return
    for child in node.children:
        _traverse_tree(child, callback)


def build_tiles_from_btree(data: SplatData, root: BTreeNode, lod_levels: int,
                           sh_degree: int = 0, comment: str = "",
                           magic: str = "splat-lod", version: int = 1) -> Tuple[SplatTiles, LodMeta]:
    files: List[SplatFile] = []
    seq_counter = [0]

    def _merge_file(merge_node: BTreeNode, lod: int) -> SplatFile:
        leafs: List[BTreeNode] = []
        total_count = 0

        def collect_leaves(n: BTreeNode) -> bool:
            nonlocal total_count
            if n.is_leaf and n.lod_counts.get(lod, 0) > 0:
                leafs.append(n)
                total_count += n.lod_counts[lod]
            return True

        _traverse_tree(merge_node, collect_leaves)

        file_key = f"{lod}_{seq_counter[0]}"
        seq_counter[0] += 1
        splat_file = SplatFile(
            file_key=file_key, index=-1, url="",
            lod=lod, seq=seq_counter[0] - 1, count=total_count,
            datas=SplatData(0),
        )

        offset = 0
        for leaf in leafs:
            lod_lods = leaf.lods[lod]
            if lod_lods is None:
                continue
            lod_lods.file_key = file_key
            lod_lods.offset = offset
            lod_lods.count = leaf.lod_counts[lod]
            if lod_lods.datas is not None:
                sort_morton(lod_lods.datas)  # sort by Morton
                if splat_file.datas is not None:
                    splat_file.datas.append(lod_lods.datas)
            offset += lod_lods.count

        files.append(splat_file)
        return splat_file

    for lod in range(lod_levels):
        seq_counter[0] = 0  # match Go: reset seq per LOD level
        merge_nodes: List[BTreeNode] = []

        def collect_merge(n: BTreeNode) -> bool:
            if n.lod_counts.get(lod, 0) > 0 and n.lod_counts.get(lod, 0) <= FILE_SPLAT_COUNT_THRESHOLD:
                merge_nodes.append(n)
                return False
            return True

        _traverse_tree(root, collect_merge)
        for mn in merge_nodes:
            _merge_file(mn, lod)

    files.sort(key=lambda f: (f.lod, f.seq))
    file_map = {f.file_key: f for f in files}
    for i, f in enumerate(files):
        f.index = i
        f.url = f"{f.lod}_{f.seq}.sog"

    root_splat = SplatNode(
        center=[root.mm.center_x, root.mm.center_y, root.mm.center_z],
        radius=root.mm.radius,
    )
    _copy_to_splat_tree(root, root_splat)

    tiles = SplatTiles(
        version=version, magic=magic, lod_levels=lod_levels,
        total_count=data.count, files=file_map, tree=root_splat,
        sh_degree=sh_degree, comment=comment,
    )

    _propagate_bounds(tiles.tree)

    lod_meta = _build_lod_meta(tiles)
    return tiles, lod_meta


def _propagate_bounds(node: SplatNode) -> Optional[Bound]:
    """Propagate bounds from leaves to root matching Go's setSplatTreeBound."""
    if node.bound is not None:
        return node.bound
    if node.lods is not None:
        return node.bound
    if node.children is None or len(node.children) == 0:
        return None
    child_bounds = [b for child in node.children if (b := _propagate_bounds(child)) is not None]
    if not child_bounds:
        return None
    mins = [min(b.min[i] for b in child_bounds) for i in range(3)]
    maxs = [max(b.max[i] for b in child_bounds) for i in range(3)]
    node.bound = Bound(min=mins, max=maxs)
    return node.bound


def _copy_to_splat_tree(bnode: BTreeNode, snode: SplatNode) -> None:
    snode.center = [bnode.mm.center_x, bnode.mm.center_y, bnode.mm.center_z]
    snode.radius = bnode.mm.radius
    if bnode.is_leaf:
        snode.lods = [t for t in bnode.lods if t is not None]  # type: ignore[assignment]
        # Compute per-leaf bound from the BTreeNode's actual point bbox
        # (matches Go's calcLodMetaBound which computes AABB per leaf node)
        snode.bound = Bound(
            min=[bnode.mm.min_x, bnode.mm.min_y, bnode.mm.min_z],
            max=[bnode.mm.max_x, bnode.mm.max_y, bnode.mm.max_z],
        )
    else:
        snode.children = []
        for child in bnode.children:
            cn = SplatNode()
            snode.children.append(cn)
            _copy_to_splat_tree(child, cn)


def _build_lod_meta(tiles: SplatTiles) -> LodMeta:
    filenames = [tiles.files[k].url for k in sorted(tiles.files.keys(), key=lambda x: (tiles.files[x].lod, tiles.files[x].seq))]

    root_lod = LodNode()
    _copy_to_lod_tree(tiles, tiles.tree, root_lod)

    return LodMeta(
        lod_levels=tiles.lod_levels,
        filenames=filenames,
        environment=tiles.environment,
        tree=root_lod,
    )


def _copy_to_lod_tree(tiles: SplatTiles, snode: SplatNode, lod_node: LodNode) -> None:
    lod_node.bound = snode.bound
    if snode.lods is not None:
        lods = {}
        for tm in snode.lods:
            if tm.file_key:
                splat_file = tiles.files.get(tm.file_key)
                if splat_file is not None:
                    lods[str(splat_file.lod)] = LodMapping(
                        file=splat_file.index, offset=tm.offset, count=tm.count
                    )
        lod_node.lods = lods
    else:
        lod_node.children = []
        if snode.children:
            for child in snode.children:
                cn = LodNode()
                lod_node.children.append(cn)
                _copy_to_lod_tree(tiles, child, cn)


def lod_meta_to_json(meta: LodMeta) -> str:
    obj = {
        "lodLevels": meta.lod_levels,
        "filenames": meta.filenames,
    }
    if meta.environment:
        obj["environment"] = meta.environment
    if meta.tree is not None:
        obj["tree"] = _lod_node_to_dict(meta.tree)
    return json.dumps(obj)


def _lod_node_to_dict(node: LodNode) -> dict:
    d = {}
    if node.bound is not None:
        d["bound"] = {"min": [round(v, 6) for v in node.bound.min],
                       "max": [round(v, 6) for v in node.bound.max]}
    if node.lods is not None:
        json_lods: Any = {
            k: {"file": v.file, "offset": v.offset, "count": v.count}
            for k, v in node.lods.items()
        }
        d["lods"] = json_lods
    if node.children is not None:
        d["children"] = [_lod_node_to_dict(c) for c in node.children]  # type: ignore[assignment]
    return d


def lod_meta_from_json(json_str: str) -> LodMeta:
    obj = json.loads(json_str)
    meta = LodMeta(
        lod_levels=obj.get("lodLevels", 0),
        filenames=obj.get("filenames", []),
        environment=obj.get("environment", ""),
    )
    if "tree" in obj:
        meta.tree = _lod_node_from_dict(obj["tree"])
    return meta


def _lod_node_from_dict(d: dict) -> LodNode:
    node = LodNode()
    if "bound" in d:
        bind = d["bound"]
        node.bound = Bound(min=bind.get("min", []), max=bind.get("max", []))
    if "lods" in d:
        node.lods = {
            k: LodMapping(file=v["file"], offset=v["offset"], count=v["count"])
            for k, v in d["lods"].items()
        }
    if "children" in d:
        node.children = [_lod_node_from_dict(c) for c in d["children"]]
    return node

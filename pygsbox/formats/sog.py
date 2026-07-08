import os
import json
import math
import numpy as np
from typing import Tuple, Optional, Dict, List
from ..core.splat_data import SplatData
from ..core.morton import V3MinMax, compute_xyz_log_min_max
from ..common import codec, compress, file_utils


class SogMetaMeans:
    def __init__(self):
        self.shape: List[int] = []
        self.dtype: str = ""
        self.mins: List[float] = []
        self.maxs: List[float] = []
        self.files: List[str] = []


class SogMetaScales:
    def __init__(self):
        self.shape: List[int] = []
        self.dtype: str = ""
        self.mins: List[float] = []
        self.maxs: List[float] = []
        self.codebook: List[float] = []
        self.files: List[str] = []


class SogMetaQuats:
    def __init__(self):
        self.shape: List[int] = []
        self.dtype: str = ""
        self.encoding: str = ""
        self.files: List[str] = []


class SogMetaSh0:
    def __init__(self):
        self.shape: List[int] = []
        self.dtype: str = ""
        self.mins: List[float] = []
        self.maxs: List[float] = []
        self.codebook: List[float] = []
        self.files: List[str] = []


class SogMetaShN:
    def __init__(self):
        self.shape: List[int] = []
        self.dtype: str = ""
        self.mins: float = 0.0
        self.maxs: float = 0.0
        self.quantization: int = 0
        self.count: int = 0
        self.bands: int = 0
        self.codebook: List[float] = []
        self.files: List[str] = []


class SogMeta:
    def __init__(self):
        self.version: int = 0
        self.count: int = 0
        self.means: Optional[SogMetaMeans] = None
        self.scales: Optional[SogMetaScales] = None
        self.quats: Optional[SogMetaQuats] = None
        self.sh0: Optional[SogMetaSh0] = None
        self.shN: Optional[SogMetaShN] = None


class SogHeader:
    def __init__(self):
        self.version: int = 0
        self.count: int = 0
        self.sh_degree: int = 0
        self.palette_size: int = 0


def _parse_sog_meta(json_str: str) -> SogMeta:
    obj = json.loads(json_str)
    meta = SogMeta()
    meta.version = obj.get("version", 0)
    meta.count = obj.get("count", 0)

    if "means" in obj:
        mm = obj["means"]
        meta.means = SogMetaMeans()
        meta.means.shape = mm.get("shape", [])
        meta.means.dtype = mm.get("dtype", "")
        meta.means.mins = mm.get("mins", [])
        meta.means.maxs = mm.get("maxs", [])
        meta.means.files = mm.get("files", [])

    if "scales" in obj:
        sc = obj["scales"]
        meta.scales = SogMetaScales()
        meta.scales.codebook = sc.get("codebook", [])
        meta.scales.files = sc.get("files", [])

    if "quats" in obj:
        q = obj["quats"]
        meta.quats = SogMetaQuats()
        meta.quats.files = q.get("files", [])

    if "sh0" in obj:
        s = obj["sh0"]
        meta.sh0 = SogMetaSh0()
        meta.sh0.codebook = s.get("codebook", [])
        meta.sh0.files = s.get("files", [])

    if "shN" in obj:
        sn = obj["shN"]
        meta.shN = SogMetaShN()
        meta.shN.count = sn.get("count", 0)
        meta.shN.bands = sn.get("bands", 0)
        meta.shN.codebook = sn.get("codebook", [])
        meta.shN.files = sn.get("files", [])

    return meta


def _read_webp_rgba(dir_path: str, filename: str) -> Tuple[bytes, int]:
    file_path = os.path.join(dir_path, filename)
    raw_data = file_utils.read_file_bytes(file_path)
    rgba, w, h = compress.decompress_webp(raw_data)
    return rgba, w


def read_sog(sog_or_meta_path: str) -> Tuple[SogHeader, SplatData]:
    dir_path = file_utils.dir_name(sog_or_meta_path)

    if sog_or_meta_path.lower().endswith(".sog"):
        tmp_dir = file_utils.create_temp_dir("sog")
        compress.unzip_file(sog_or_meta_path, tmp_dir)
        dir_path = tmp_dir
        sog_or_meta_path = os.path.join(tmp_dir, "meta.json")

    meta_str = file_utils.read_file_string(sog_or_meta_path)
    meta = _parse_sog_meta(meta_str)

    if meta.version == 0:
        return _read_sog_v1(meta, dir_path)
    elif meta.version == 2:
        return _read_sog_v2(meta, dir_path)
    else:
        raise ValueError(f"Unsupported SOG version: {meta.version}")


def _read_sog_v1(meta: SogMeta, dir_path: str) -> Tuple[SogHeader, SplatData]:
    assert meta.means is not None
    assert meta.scales is not None
    assert meta.quats is not None
    assert meta.sh0 is not None
    meansl, _ = _read_webp_rgba(dir_path, meta.means.files[0])
    meansu, _ = _read_webp_rgba(dir_path, meta.means.files[1])
    scales, _ = _read_webp_rgba(dir_path, meta.scales.files[0])
    quats, _ = _read_webp_rgba(dir_path, meta.quats.files[0])
    sh0, _ = _read_webp_rgba(dir_path, meta.sh0.files[0])

    centroids = b''
    centroids_width = 0
    labels = b''
    if meta.shN is not None:
        centroids, centroids_width = _read_webp_rgba(dir_path, meta.shN.files[0])

    count = meta.means.shape[0]
    data = SplatData(count)

    sh_degree = 0
    if meta.shN is not None:
        dim = meta.shN.shape[1] if len(meta.shN.shape) > 1 else 0
        if dim in (45, 15):
            sh_degree = 3
        elif dim in (24, 8):
            sh_degree = 2
        elif dim in (9, 3):
            sh_degree = 1

    labels_data = b''
    if sh_degree > 0 and meta.shN is not None and len(meta.shN.files) > 1:
        labels_data, _ = _read_webp_rgba(dir_path, meta.shN.files[1])

    mins = meta.means.mins
    maxs = meta.means.maxs

    for i in range(count):
        fx = ((meansu[i * 4 + 0] << 8) | meansl[i * 4 + 0]) / 65535.0
        fy = ((meansu[i * 4 + 1] << 8) | meansl[i * 4 + 1]) / 65535.0
        fz = ((meansu[i * 4 + 2] << 8) | meansl[i * 4 + 2]) / 65535.0

        x = mins[0] + (maxs[0] - mins[0]) * fx
        y = mins[1] + (maxs[1] - mins[1]) * fy
        z = mins[2] + (maxs[2] - mins[2]) * fz

        x = codec.decode_log(x)
        y = codec.decode_log(y)
        z = codec.decode_log(z)

        data.position[i, 0] = x
        data.position[i, 1] = y
        data.position[i, 2] = z

        sx = scales[i * 4 + 0] / 255.0
        sy = scales[i * 4 + 1] / 255.0
        sz = scales[i * 4 + 2] / 255.0
        data.scale[i, 0] = meta.scales.mins[0] + (meta.scales.maxs[0] - meta.scales.mins[0]) * sx
        data.scale[i, 1] = meta.scales.mins[1] + (meta.scales.maxs[1] - meta.scales.mins[1]) * sy
        data.scale[i, 2] = meta.scales.mins[2] + (meta.scales.maxs[2] - meta.scales.mins[2]) * sz

        data.rotation[i] = list(codec.sog_decode_rotations(
            quats[i * 4 + 0], quats[i * 4 + 1],
            quats[i * 4 + 2], quats[i * 4 + 3]
        ))

        r = meta.sh0.mins[0] + (meta.sh0.maxs[0] - meta.sh0.mins[0]) * (sh0[i * 4 + 0] / 255.0)
        g = meta.sh0.mins[1] + (meta.sh0.maxs[1] - meta.sh0.mins[1]) * (sh0[i * 4 + 1] / 255.0)
        b = meta.sh0.mins[2] + (meta.sh0.maxs[2] - meta.sh0.mins[2]) * (sh0[i * 4 + 2] / 255.0)
        a = meta.sh0.mins[3] + (meta.sh0.maxs[3] - meta.sh0.mins[3]) * (sh0[i * 4 + 3] / 255.0)
        data.color[i, 0] = codec.encode_splat_color(r)
        data.color[i, 1] = codec.encode_splat_color(g)
        data.color[i, 2] = codec.encode_splat_color(b)
        data.color[i, 3] = codec.encode_splat_opacity(a)

        if sh_degree > 0 and len(labels_data) > 0:
            assert meta.shN is not None
            label = labels_data[i * 4 + 0] | (labels_data[i * 4 + 1] << 8)
            col = label & 63
            row = label >> 6
            offset = row * centroids_width + col * 15
            sh_dims_list = [0, 3, 8, 15]
            sh_dim = sh_dims_list[sh_degree]
            sh_values = []
            for d in range(3):
                for sd in range(sh_degree):
                    for k in range([3, 5, 7][sd]):
                        sh_base = 0 if sd == 0 else (3 if sd == 1 else 8)
                        idx = sh_base + k
                        for dc in range(3):
                            val = (meta.shN.maxs - meta.shN.mins) * centroids[(offset + idx) * 4 + dc] / 255.0 + meta.shN.mins
                            sh_values.append(codec.encode_splat_sh(val))
            for vi in range(min(len(sh_values), 45)):
                data.sh[i, vi] = sh_values[vi]
            data.palette_idx[i] = label

    header = SogHeader()
    header.version = 1
    header.count = count
    header.sh_degree = sh_degree
    return header, data


def _read_sog_v2(meta: SogMeta, dir_path: str) -> Tuple[SogHeader, SplatData]:
    assert meta.means is not None
    assert meta.scales is not None
    assert meta.quats is not None
    assert meta.sh0 is not None
    meansl, _ = _read_webp_rgba(dir_path, meta.means.files[0])
    meansu, _ = _read_webp_rgba(dir_path, meta.means.files[1])
    scales, _ = _read_webp_rgba(dir_path, meta.scales.files[0])
    quats, _ = _read_webp_rgba(dir_path, meta.quats.files[0])
    sh0, _ = _read_webp_rgba(dir_path, meta.sh0.files[0])

    centroids = b''
    centroids_width = 0
    labels = b''
    palette_size = 0
    if meta.shN is not None:
        centroids, centroids_width = _read_webp_rgba(dir_path, meta.shN.files[0])
        palette_size = meta.shN.count if meta.shN.count > 0 else 65536

    count = meta.count
    data = SplatData(count)

    sh_degree = 0
    if meta.shN is not None:
        if meta.shN.count > 0 and meta.shN.bands > 0:
            sh_degree = meta.shN.bands
        else:
            sh_degree = 3

    labels_data = b''
    if sh_degree > 0 and meta.shN is not None and len(meta.shN.files) > 1:
        labels_data, _ = _read_webp_rgba(dir_path, meta.shN.files[1])

    mins = meta.means.mins
    maxs = meta.means.maxs

    for i in range(count):
        fx = ((meansu[i * 4 + 0] << 8) | meansl[i * 4 + 0]) / 65535.0
        fy = ((meansu[i * 4 + 1] << 8) | meansl[i * 4 + 1]) / 65535.0
        fz = ((meansu[i * 4 + 2] << 8) | meansl[i * 4 + 2]) / 65535.0

        x = mins[0] + (maxs[0] - mins[0]) * fx
        y = mins[1] + (maxs[1] - mins[1]) * fy
        z = mins[2] + (maxs[2] - mins[2]) * fz

        x = codec.decode_log(x)
        y = codec.decode_log(y)
        z = codec.decode_log(z)

        data.position[i, 0] = x
        data.position[i, 1] = y
        data.position[i, 2] = z

        sx = meta.scales.codebook[scales[i * 4 + 0]]
        sy = meta.scales.codebook[scales[i * 4 + 1]]
        sz = meta.scales.codebook[scales[i * 4 + 2]]
        data.scale[i, 0] = sx
        data.scale[i, 1] = sy
        data.scale[i, 2] = sz

        data.rotation[i] = list(codec.sog_decode_rotations(
            quats[i * 4 + 0], quats[i * 4 + 1],
            quats[i * 4 + 2], quats[i * 4 + 3]
        ))

        r = meta.sh0.codebook[sh0[i * 4 + 0]]
        g = meta.sh0.codebook[sh0[i * 4 + 1]]
        b_val = meta.sh0.codebook[sh0[i * 4 + 2]]
        a_val = sh0[i * 4 + 3]
        data.color[i, 0] = codec.encode_splat_color(r)
        data.color[i, 1] = codec.encode_splat_color(g)
        data.color[i, 2] = codec.encode_splat_color(b_val)
        data.color[i, 3] = a_val

        if sh_degree > 0 and len(labels_data) > 0:
            assert meta.shN is not None
            sh_dims = [0, 3, 8, 15]
            sh_dim = sh_dims[sh_degree]
            label = labels_data[i * 4 + 0] | (labels_data[i * 4 + 1] << 8)
            col = label & 63
            row = label >> 6
            pixel_offset = row * centroids_width + col * sh_dim

            for k in range(sh_dim):
                f32_r = meta.shN.codebook[centroids[(pixel_offset + k) * 4 + 0]]
                f32_g = meta.shN.codebook[centroids[(pixel_offset + k) * 4 + 1]]
                f32_b = meta.shN.codebook[centroids[(pixel_offset + k) * 4 + 2]]
                data.sh[i, k * 3 + 0] = codec.encode_splat_sh(f32_r)
                data.sh[i, k * 3 + 1] = codec.encode_splat_sh(f32_g)
                data.sh[i, k * 3 + 2] = codec.encode_splat_sh(f32_b)

            data.palette_idx[i] = label

    header = SogHeader()
    header.version = 2
    header.count = count
    header.sh_degree = sh_degree
    header.palette_size = palette_size
    return header, data


def write_sog(sog_or_json_path: str, data: SplatData, sh_degree: int = 0, as_zip: bool = True, quality: int = 5):
    os.makedirs(os.path.dirname(os.path.abspath(sog_or_json_path)) or '.', exist_ok=True)

    from ..common.progress import Progress, PHASE_WRITE

    dir_path = file_utils.dir_name(sog_or_json_path)
    is_sog = not sog_or_json_path.lower().endswith("meta.json")

    if is_sog:
        tmp_dir = file_utils.create_temp_dir("sog_write")
        work_dir = tmp_dir
    else:
        work_dir = dir_path

    files = []

    Progress.report(PHASE_WRITE, 0, 100)
    means_files, mm = _write_sog_means(work_dir, data)
    files.extend(means_files)
    Progress.report(PHASE_WRITE, 25, 100)

    files.extend(_write_sog_scales(work_dir, data))
    Progress.report(PHASE_WRITE, 40, 100)

    files.extend(_write_sog_quats(work_dir, data))
    Progress.report(PHASE_WRITE, 55, 100)

    files.extend(_write_sog_sh0(work_dir, data))
    Progress.report(PHASE_WRITE, 70, 100)

    palette_size = 0
    if sh_degree > 0:
        shN_files, palette_size = _write_sog_shN(work_dir, data, sh_degree, quality=quality)
        files.extend(shN_files)
    Progress.report(PHASE_WRITE, 85, 100)

    _write_sog_meta(work_dir, data, mm, palette_size, sh_degree)
    meta_file = os.path.join(work_dir, "meta.json")
    files.append(meta_file)

    if is_sog:
        compress.zip_files(sog_or_json_path, files)
    return


def _write_sog_means(dir_path: str, data: SplatData) -> Tuple[List[str], V3MinMax]:
    mm = compute_xyz_log_min_max(data)
    count = data.count

    means_l = bytearray(count * 4)
    means_u = bytearray(count * 4)

    for i in range(count):
        x = codec.clip_uint16(65535.0 * (codec.sog_encode_log(float(data.position[i, 0])) - mm.min_x) / mm.len_x + 0.5)
        y = codec.clip_uint16(65535.0 * (codec.sog_encode_log(float(data.position[i, 1])) - mm.min_y) / mm.len_y + 0.5)
        z = codec.clip_uint16(65535.0 * (codec.sog_encode_log(float(data.position[i, 2])) - mm.min_z) / mm.len_z + 0.5)

        means_l[i * 4 + 0] = x & 0xFF
        means_l[i * 4 + 1] = y & 0xFF
        means_l[i * 4 + 2] = z & 0xFF
        means_l[i * 4 + 3] = 255

        means_u[i * 4 + 0] = x >> 8
        means_u[i * 4 + 1] = y >> 8
        means_u[i * 4 + 2] = z >> 8
        means_u[i * 4 + 3] = 255

    path_l = os.path.join(dir_path, "means_l.webp")
    path_u = os.path.join(dir_path, "means_u.webp")

    webp_l = compress.compress_webp(bytes(means_l))
    webp_u = compress.compress_webp(bytes(means_u))

    file_utils.write_file_bytes(path_l, webp_l)
    file_utils.write_file_bytes(path_u, webp_u)

    return [path_l, path_u], mm


def _write_sog_scales(dir_path: str, data: SplatData) -> List[str]:
    count = data.count
    rgba = bytearray(count * 4)
    for i in range(count):
        rgba[i * 4 + 0] = codec.encode_spx_scale(float(data.scale[i, 0]))
        rgba[i * 4 + 1] = codec.encode_spx_scale(float(data.scale[i, 1]))
        rgba[i * 4 + 2] = codec.encode_spx_scale(float(data.scale[i, 2]))
        rgba[i * 4 + 3] = 255
    webp = compress.compress_webp(bytes(rgba))
    path = os.path.join(dir_path, "scales.webp")
    file_utils.write_file_bytes(path, webp)
    return [path]


def _write_sog_quats(dir_path: str, data: SplatData) -> List[str]:
    count = data.count
    rgba = bytearray(count * 4)
    for i in range(count):
        r, g, b, a = codec.sog_encode_rotations(
            int(data.rotation[i, 0]), int(data.rotation[i, 1]),
            int(data.rotation[i, 2]), int(data.rotation[i, 3])
        )
        rgba[i * 4 + 0] = r
        rgba[i * 4 + 1] = g
        rgba[i * 4 + 2] = b
        rgba[i * 4 + 3] = a
    webp = compress.compress_webp(bytes(rgba))
    path = os.path.join(dir_path, "quats.webp")
    file_utils.write_file_bytes(path, webp)
    return [path]


def _write_sog_sh0(dir_path: str, data: SplatData) -> List[str]:
    count = data.count
    rgba = bytearray(count * 4)
    for i in range(count):
        rgba[i * 4 + 0] = int(data.color[i, 0])
        rgba[i * 4 + 1] = int(data.color[i, 1])
        rgba[i * 4 + 2] = int(data.color[i, 2])
        rgba[i * 4 + 3] = int(data.color[i, 3])
    webp = compress.compress_webp(bytes(rgba))
    path = os.path.join(dir_path, "sh0.webp")
    file_utils.write_file_bytes(path, webp)
    return [path]


def _write_sog_shN(dir_path: str, data: SplatData, sh_degree: int, quality: int = 5) -> Tuple[List[str], int]:
    if data.count == 0:
        return [], 0

    from ..advanced.kmeans import rewrite_sh_by_kmeans, build_labels_image

    sh_dim_map = {1: 3, 2: 8, 3: 15}
    sh_dim = sh_dim_map.get(sh_degree, 15)
    width_map = {1: 96, 2: 512, 3: 960}
    centroids_width = width_map.get(sh_degree, 960)

    centroids, labels, palette_size = rewrite_sh_by_kmeans(data, sh_degree, quality=quality)

    if centroids is None or palette_size == 0:
        return [], 0

    assert labels is not None
    centroids_rgba = bytearray(palette_size * sh_dim * 4)
    for i in range(palette_size):
        base = i * sh_dim * 4
        for k in range(sh_dim):
            pixel_off = base + k * 4
            centroids_rgba[pixel_off + 0] = int(centroids[i, k * 3 + 0])
            centroids_rgba[pixel_off + 1] = int(centroids[i, k * 3 + 1])
            centroids_rgba[pixel_off + 2] = int(centroids[i, k * 3 + 2])
            centroids_rgba[pixel_off + 3] = 255

    webp_centroids = compress.compress_webp(
        bytes(centroids_rgba),
        width=centroids_width, height=1024,
    )

    labels_rgba = build_labels_image(labels, data.count)
    webp_labels = compress.compress_webp(bytes(labels_rgba))

    centroids_path = os.path.join(dir_path, "shN_centroids.webp")
    labels_path = os.path.join(dir_path, "shN_labels.webp")
    file_utils.write_file_bytes(centroids_path, webp_centroids)
    file_utils.write_file_bytes(labels_path, webp_labels)

    return [centroids_path, labels_path], palette_size


def _write_sog_meta(dir_path: str, data: SplatData, mm: V3MinMax, palette_size: int, sh_degree: int):
    scale_codebook = [codec.decode_spx_scale(i) for i in range(256)]
    sh0_codebook = [codec.decode_splat_color(i) for i in range(256)]

    meta = {
        "version": 2,
        "count": data.count,
        "means": {
            "mins": [mm.min_x, mm.min_y, mm.min_z],
            "maxs": [mm.max_x, mm.max_y, mm.max_z],
            "files": ["means_l.webp", "means_u.webp"],
        },
        "scales": {
            "codebook": scale_codebook,
            "files": ["scales.webp"],
        },
        "quats": {
            "files": ["quats.webp"],
        },
        "sh0": {
            "codebook": sh0_codebook,
            "files": ["sh0.webp"],
        },
    }

    if palette_size > 0 and sh_degree > 0:
        shn_codebook = [codec.decode_splat_sh(i) for i in range(256)]
        meta["shN"] = {
            "count": palette_size,
            "bands": sh_degree,
            "codebook": shn_codebook,
            "files": ["shN_centroids.webp", "shN_labels.webp"],
        }

    meta_path = os.path.join(dir_path, "meta.json")
    file_utils.write_file_string(meta_path, json.dumps(meta))

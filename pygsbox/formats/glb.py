import os
import json
import struct
import numpy as np
from typing import Tuple, Dict, Any, Optional
from ..core.splat_data import SplatData
from ..core.morton import compute_xyz_min_max, V3MinMax
from ..common import codec, compress
from ..common.version import VER

KHR_GAUSSIAN_SPLATTING = "KHR_gaussian_splatting"
KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2 = "KHR_gaussian_splatting_compression_spz_2"
COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY = "com_github_gotoeasy_gsbox_webp_rgb_ply"

GLB_MAGIC = b'glTF'
GLB_VERSION = 2
GLB_JSON_TYPE = 0x4E4F534A
GLB_BIN_TYPE = 0x004E4942


def read_glb(file_path: str) -> Tuple[int, SplatData]:
    with open(file_path, 'rb') as f:
        header = f.read(20)

    json_length = struct.unpack('<I', header[12:16])[0]
    json_length_aligned = (json_length + 3) & ~3

    with open(file_path, 'rb') as f:
        f.seek(20)
        json_bytes = f.read(json_length_aligned)

    json_str = json_bytes[:json_length].decode('utf-8', errors='ignore')

    if KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2 in json_str:
        return _read_glb_spz(file_path, json_str)
    elif COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY in json_str:
        return _read_glb_rgb_ply(file_path, json_str)
    elif KHR_GAUSSIAN_SPLATTING in json_str:
        return _read_glb_khr(file_path, json_str)
    else:
        raise ValueError("Unsupported GLB extension")


def _read_glb_spz(file_path: str, json_str: str) -> Tuple[int, SplatData]:
    gltf = json.loads(json_str)
    byte_length = gltf["bufferViews"][0]["byteLength"]

    with open(file_path, 'rb') as f:
        f.seek(20 + _json_chunk_size(json_str))
        bin_header = f.read(8)
        spz_data = f.read(byte_length)

    from .spz import SPZ_MAGIC
    decompressed = compress.decompress_gzip(spz_data)
    if len(decompressed) < 16:
        raise ValueError("Invalid SPZ data inside GLB")

    magic = struct.unpack('<I', decompressed[0:4])[0]
    if magic != SPZ_MAGIC:
        raise ValueError("Invalid SPZ magic inside GLB")

    version = struct.unpack('<I', decompressed[4:8])[0]
    num_points = struct.unpack('<I', decompressed[8:12])[0]
    sh_degree = decompressed[12]

    from .spz import SpzHeader, _parse_spz_header
    header = _parse_spz_header(decompressed[:16])

    from .spz import _read_spz_v2v3
    data = _read_spz_v2v3(decompressed[16:], header)

    return header.sh_degree, data


def _read_glb_rgb_ply(file_path: str, json_str: str) -> Tuple[int, SplatData]:
    gltf = json.loads(json_str)
    byte_length = gltf["bufferViews"][0]["byteLength"]

    with open(file_path, 'rb') as f:
        f.seek(20 + _json_chunk_size(json_str))
        bin_header = f.read(8)
        webp_data = f.read(byte_length)

    rgba_data, w, h = compress.decompress_webp(webp_data)

    cnt = rgba_data[0] | (rgba_data[1] << 8) | (rgba_data[2] << 16)
    splats = SplatData(cnt)
    rgbas = list(rgba_data[4:])

    from ..common.codec import decode_spx_position_uint24
    for i in range(cnt):
        idx1 = i * 4
        idx2 = cnt * 4 + i * 4
        idx3 = cnt * 8 + i * 4
        idx4 = cnt * 12 + i * 4

        x0, y0, z0 = rgbas[idx1], rgbas[idx1 + 1], rgbas[idx1 + 2]
        x1, y1, z1 = rgbas[idx2], rgbas[idx2 + 1], rgbas[idx2 + 2]
        x2, y2, z2 = rgbas[idx3], rgbas[idx3 + 1], rgbas[idx3 + 2]
        r, g, b = rgbas[idx4], rgbas[idx4 + 1], rgbas[idx4 + 2]

        splats.position[i, 0] = decode_spx_position_uint24(x0, x1, x2)
        splats.position[i, 1] = decode_spx_position_uint24(y0, y1, y2)
        splats.position[i, 2] = decode_spx_position_uint24(z0, z1, z2)
        splats.color[i, 0] = r
        splats.color[i, 1] = g
        splats.color[i, 2] = b
        splats.color[i, 3] = 255
        splats.scale[i] = [-4.6, -4.6, -4.6]
        splats.rotation[i] = [255, 128, 128, 128]

    return 0, splats


def _read_glb_khr(file_path: str, json_str: str) -> Tuple[int, SplatData]:
    gltf = json.loads(json_str)

    meshes = gltf["meshes"]
    attrs = meshes[0]["primitives"][0]["attributes"]

    splat_count = gltf["accessors"][0]["count"]

    field_map = {
        "POSITION": attrs.get("POSITION", -1),
        "SCALE": attrs.get(f"{KHR_GAUSSIAN_SPLATTING}:SCALE", -1),
        "SH0": attrs.get(f"{KHR_GAUSSIAN_SPLATTING}:SH_DEGREE_0_COEF_0", -1),
        "OPACITY": attrs.get(f"{KHR_GAUSSIAN_SPLATTING}:OPACITY", -1),
        "ROTATION": attrs.get(f"{KHR_GAUSSIAN_SPLATTING}:ROTATION", -1),
    }

    sh_degree = 0
    sh_field_indices = {}

    for d1 in range(3):
        key = f"{KHR_GAUSSIAN_SPLATTING}:SH_DEGREE_1_COEF_{d1}"
        idx = attrs.get(key, -1)
        if idx >= 0:
            sh_degree = max(sh_degree, 1)
            sh_field_indices[f"sh1_{d1}"] = idx

    for d2 in range(5):
        key = f"{KHR_GAUSSIAN_SPLATTING}:SH_DEGREE_2_COEF_{d2}"
        idx = attrs.get(key, -1)
        if idx >= 0:
            sh_degree = max(sh_degree, 2)
            sh_field_indices[f"sh2_{d2}"] = idx

    for d3 in range(7):
        key = f"{KHR_GAUSSIAN_SPLATTING}:SH_DEGREE_3_COEF_{d3}"
        idx = attrs.get(key, -1)
        if idx >= 0:
            sh_degree = max(sh_degree, 3)
            sh_field_indices[f"sh3_{d3}"] = idx

    bvs = gltf["bufferViews"]

    def get_bv_offset(index):
        if index < 0 or index >= len(bvs):
            return -1
        bv = bvs[index]
        offset = bv.get("byteOffset", 0)
        return offset

    offset_position = get_bv_offset(field_map["POSITION"])
    offset_scale = get_bv_offset(field_map["SCALE"])
    offset_sh0 = get_bv_offset(field_map["SH0"])
    offset_opacity = get_bv_offset(field_map["OPACITY"])
    offset_rotation = get_bv_offset(field_map["ROTATION"])

    sh_offsets = {}
    for key, idx in sh_field_indices.items():
        sh_offsets[key] = get_bv_offset(idx)

    with open(file_path, 'rb') as f:
        f.seek(20 + _json_chunk_size(json_str))
        bin_header = f.read(8)

    bin_length = struct.unpack('<I', bin_header[0:4])[0]
    with open(file_path, 'rb') as f:
        f.seek(28 + _json_chunk_size(json_str))
        bin_data = f.read(bin_length)

    data = SplatData(splat_count)

    for i in range(splat_count):
        po = offset_position + i * 12
        data.position[i, 0] = struct.unpack('<f', bin_data[po:po + 4])[0]
        data.position[i, 1] = struct.unpack('<f', bin_data[po + 4:po + 8])[0]
        data.position[i, 2] = struct.unpack('<f', bin_data[po + 8:po + 12])[0]

        so = offset_scale + i * 12
        data.scale[i, 0] = struct.unpack('<f', bin_data[so:so + 4])[0]
        data.scale[i, 1] = struct.unpack('<f', bin_data[so + 4:so + 8])[0]
        data.scale[i, 2] = struct.unpack('<f', bin_data[so + 8:so + 12])[0]

        ro = offset_sh0 + i * 12
        r = struct.unpack('<f', bin_data[ro:ro + 4])[0]
        g = struct.unpack('<f', bin_data[ro + 4:ro + 8])[0]
        b = struct.unpack('<f', bin_data[ro + 8:ro + 12])[0]
        data.color[i, 0] = codec.encode_splat_color(float(r))
        data.color[i, 1] = codec.encode_splat_color(float(g))
        data.color[i, 2] = codec.encode_splat_color(float(b))

        oo = offset_opacity + i * 4
        opacity = struct.unpack('<f', bin_data[oo:oo + 4])[0]
        data.color[i, 3] = codec.encode_splat_opacity(float(opacity))

        rto = offset_rotation + i * 16
        rx = struct.unpack('<f', bin_data[rto:rto + 4])[0]
        ry = struct.unpack('<f', bin_data[rto + 4:rto + 8])[0]
        rz = struct.unpack('<f', bin_data[rto + 8:rto + 12])[0]
        rw = struct.unpack('<f', bin_data[rto + 12:rto + 16])[0]
        data.rotation[i, 0] = codec.encode_splat_rotation(float(rw))
        data.rotation[i, 1] = codec.encode_splat_rotation(float(rx))
        data.rotation[i, 2] = codec.encode_splat_rotation(float(ry))
        data.rotation[i, 3] = codec.encode_splat_rotation(float(rz))

    if sh_degree > 0:
        sh_indexes = [
            0, 3, 6, 1, 4, 7, 2, 5, 8,
            9, 14, 19, 10, 15, 20, 11, 16, 21, 12, 17, 22, 13, 18, 23,
            24, 31, 38, 25, 32, 39, 26, 33, 40, 27, 34, 41, 28, 35, 42, 29, 36, 43, 30, 37, 44,
        ]

        for i in range(splat_count):
            for band in range(1, sh_degree + 1):
                n_coefs = [3, 5, 7][band - 1]
                for c in range(n_coefs):
                    key = f"sh{band}_{c}"
                    if key not in sh_offsets:
                        continue
                    sh_off = sh_offsets[key]
                    if sh_off < 0:
                        continue
                    base = sh_off + i * 12
                    for dc in range(3):
                        val = struct.unpack('<f', bin_data[base + dc * 4:base + (dc + 1) * 4])[0]
                        sh_idx = sh_indexes[(band_start(band) + c) * 3 + dc]
                        data.sh[i, sh_idx] = codec.encode_splat_sh(float(val))

    return sh_degree, data


def band_start(degree: int) -> int:
    return {1: 0, 2: 3, 3: 8}[degree]


def _json_chunk_size(json_str: str) -> int:
    json_length = len(json_str.encode('utf-8'))
    return (json_length + 3) & ~3


def write_glb(file_path: str, data: SplatData, sh_degree: int = 0,
              glb_extension: str = KHR_GAUSSIAN_SPLATTING):
    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

    if glb_extension == KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2:
        _write_glb_spz(file_path, data, sh_degree)
    elif glb_extension == COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY:
        _write_glb_rgb_ply(file_path, data)
    else:
        _write_glb_khr(file_path, data, sh_degree)


def _write_glb_khr(file_path: str, data: SplatData, sh_degree: int):
    mm = compute_xyz_min_max(data)
    count = data.count

    json_obj = _build_glb_json_khr(count, mm, sh_degree)
    json_str = json.dumps(json_obj)
    json_bytes = json_str.encode('utf-8')
    json_length = len(json_bytes)
    json_length_aligned = (json_length + 3) & ~3

    bin_length = count * (12 + 4 + 16 + 12 + 4 + 12)
    if sh_degree > 0:
        bin_length += count * 12 * 3
    if sh_degree > 1:
        bin_length += count * 12 * 5
    if sh_degree > 2:
        bin_length += count * 12 * 7

    bin_length_aligned = (bin_length + 3) & ~3
    total_length = 12 + 8 + json_length_aligned + 8 + bin_length_aligned

    with open(file_path, 'wb') as f:
        f.write(GLB_MAGIC)
        f.write(struct.pack('<I', GLB_VERSION))
        f.write(struct.pack('<I', total_length))

        f.write(struct.pack('<I', json_length_aligned))
        f.write(struct.pack('<I', GLB_JSON_TYPE))
        f.write(json_bytes)
        f.write(b' ' * (json_length_aligned - json_length))

        f.write(struct.pack('<I', bin_length))
        f.write(struct.pack('<I', GLB_BIN_TYPE))

        for i in range(count):
            f.write(struct.pack('<fff',
                float(data.position[i, 0]),
                float(data.position[i, 1]),
                float(data.position[i, 2])
            ))

        for i in range(count):
            f.write(bytes([
                int(data.color[i, 0]),
                int(data.color[i, 1]),
                int(data.color[i, 2]),
                int(data.color[i, 3])
            ]))

        for i in range(count):
            f.write(struct.pack('<ffff',
                float(codec.decode_splat_rotation(int(data.rotation[i, 1]))),
                float(codec.decode_splat_rotation(int(data.rotation[i, 2]))),
                float(codec.decode_splat_rotation(int(data.rotation[i, 3]))),
                float(codec.decode_splat_rotation(int(data.rotation[i, 0])))
            ))

        for i in range(count):
            f.write(struct.pack('<fff',
                float(data.scale[i, 0]),
                float(data.scale[i, 1]),
                float(data.scale[i, 2])
            ))

        for i in range(count):
            f.write(struct.pack('<f', float(codec.decode_splat_opacity(int(data.color[i, 3])))))

        for i in range(count):
            f.write(struct.pack('<fff',
                float(codec.decode_splat_color(int(data.color[i, 0]))),
                float(codec.decode_splat_color(int(data.color[i, 1]))),
                float(codec.decode_splat_color(int(data.color[i, 2])))
            ))

        if sh_degree > 0:
            for c in range(3):
                for i in range(count):
                    r = float(codec.decode_splat_sh(int(data.sh[i, c * 3 + 0])))
                    g = float(codec.decode_splat_sh(int(data.sh[i, c * 3 + 1])))
                    b = float(codec.decode_splat_sh(int(data.sh[i, c * 3 + 2])))
                    f.write(struct.pack('<fff', r, g, b))

        if sh_degree > 1:
            for c in range(5):
                for i in range(count):
                    r = float(codec.decode_splat_sh(int(data.sh[i, (3 + c) * 3 + 0])))
                    g = float(codec.decode_splat_sh(int(data.sh[i, (3 + c) * 3 + 1])))
                    b = float(codec.decode_splat_sh(int(data.sh[i, (3 + c) * 3 + 2])))
                    f.write(struct.pack('<fff', r, g, b))

        if sh_degree > 2:
            for c in range(7):
                for i in range(count):
                    r = float(codec.decode_splat_sh(int(data.sh[i, (8 + c) * 3 + 0])))
                    g = float(codec.decode_splat_sh(int(data.sh[i, (8 + c) * 3 + 1])))
                    b = float(codec.decode_splat_sh(int(data.sh[i, (8 + c) * 3 + 2])))
                    f.write(struct.pack('<fff', r, g, b))

        f.write(b'\x00' * (bin_length_aligned - bin_length))


def _build_glb_json_khr(count: int, mm: V3MinMax, sh_degree: int) -> dict:
    accessors = [
        {
            "bufferView": 0, "byteOffset": 0, "componentType": 5126,
            "count": count, "min": [mm.min_x, mm.min_y, mm.min_z],
            "max": [mm.max_x, mm.max_y, mm.max_z], "type": "VEC3"
        },
        {
            "bufferView": 1, "byteOffset": 0, "componentType": 5121,
            "count": count, "normalized": True, "type": "VEC4"
        },
        {
            "bufferView": 2, "byteOffset": 0, "componentType": 5126,
            "count": count, "type": "VEC4"
        },
        {
            "bufferView": 3, "byteOffset": 0, "componentType": 5126,
            "count": count, "type": "VEC3"
        },
        {
            "bufferView": 4, "byteOffset": 0, "componentType": 5126,
            "count": count, "type": "SCALAR"
        },
        {
            "bufferView": 5, "byteOffset": 0, "componentType": 5126,
            "count": count, "type": "VEC3"
        },
    ]

    buffer_views = [
        {"buffer": 0, "byteLength": count * 12, "byteOffset": 0, "target": 34962},
        {"buffer": 0, "byteLength": count * 4, "byteOffset": 0, "target": 34962},
        {"buffer": 0, "byteLength": count * 16, "byteOffset": 0, "target": 34962},
        {"buffer": 0, "byteLength": count * 12, "byteOffset": 0, "target": 34962},
        {"buffer": 0, "byteLength": count * 4, "byteOffset": 0, "target": 34962},
        {"buffer": 0, "byteLength": count * 12, "byteOffset": 0, "target": 34962},
    ]

    attributes = {
        "POSITION": 0,
        "COLOR_0": 1,
        f"{KHR_GAUSSIAN_SPLATTING}:ROTATION": 2,
        f"{KHR_GAUSSIAN_SPLATTING}:SCALE": 3,
        f"{KHR_GAUSSIAN_SPLATTING}:OPACITY": 4,
        f"{KHR_GAUSSIAN_SPLATTING}:SH_DEGREE_0_COEF_0": 5,
    }

    max_index = 6
    offset = count * 12 + count * 4 + count * 16 + count * 12 + count * 4 + count * 12

    sh_configs = [
        (1, 3, "SH_DEGREE_1"),
        (2, 5, "SH_DEGREE_2"),
        (3, 7, "SH_DEGREE_3"),
    ]

    for degree, n_coefs, prefix in sh_configs:
        if sh_degree >= degree:
            for c in range(n_coefs):
                attr_name = f"{KHR_GAUSSIAN_SPLATTING}:{prefix}_COEF_{c}"
                attributes[attr_name] = max_index
                accessors.append({
                    "bufferView": max_index, "byteOffset": 0,
                    "componentType": 5126, "count": count, "type": "VEC3"
                })
                buffer_views.append({
                    "buffer": 0, "byteLength": count * 12,
                    "byteOffset": offset, "target": 34962
                })
                offset += count * 12
                max_index += 1

    result = {
        "asset": {"generator": f"pygsbox {VER}", "version": "2.0"},
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": offset}],
        "extensionsUsed": [KHR_GAUSSIAN_SPLATTING],
        "meshes": [{
            "primitives": [{
                "attributes": attributes,
                "extensions": {
                    KHR_GAUSSIAN_SPLATTING: {
                        "colorSpace": "srgb_rec709_display",
                        "kernel": "ellipse",
                        "projection": "perspective",
                        "sortingMethod": "cameraDistance"
                    }
                },
                "mode": 0
            }]
        }],
        "nodes": [{"mesh": 0}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }

    return result


def _write_glb_spz(file_path: str, data: SplatData, sh_degree: int):
    from .spz import SPZ_MAGIC, SpzHeader, _spz_header_to_bytes
    from .spz import _write_spz_v2v3

    import io
    buf = io.BytesIO()
    _write_spz_v2v3(file_path, data, sh_degree, 3)

    with open(file_path, 'rb') as f:
        spz_compressed = f.read()

    json_obj = {
        "asset": {"generator": f"pygsbox {VER}", "version": "2.0"},
        "bufferViews": [{"buffer": 0, "byteLength": len(spz_compressed)}],
        "buffers": [{"byteLength": len(spz_compressed)}],
        "extensions": {},
        "extensionsRequired": [
            KHR_GAUSSIAN_SPLATTING,
            KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2
        ],
        "extensionsUsed": [
            KHR_GAUSSIAN_SPLATTING,
            KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2
        ],
        "meshes": [{
            "primitives": [{
                "attributes": {},
                "extensions": {
                    KHR_GAUSSIAN_SPLATTING: {
                        "extensions": {
                            KHR_GAUSSIAN_SPLATTING_COMPRESSION_SPZ_2: {
                                "bufferView": 0
                            }
                        }
                    }
                },
                "mode": 0
            }]
        }],
        "nodes": [{"mesh": 0}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }

    json_str = json.dumps(json_obj)
    json_bytes = json_str.encode('utf-8')
    json_length = len(json_bytes)
    json_length_aligned = (json_length + 3) & ~3

    bin_length = len(spz_compressed)
    bin_length_aligned = (bin_length + 3) & ~3

    total_length = 12 + 8 + json_length_aligned + 8 + bin_length_aligned

    with open(file_path, 'wb') as f:
        f.write(GLB_MAGIC)
        f.write(struct.pack('<I', GLB_VERSION))
        f.write(struct.pack('<I', total_length))

        f.write(struct.pack('<I', json_length_aligned))
        f.write(struct.pack('<I', GLB_JSON_TYPE))
        f.write(json_bytes)
        f.write(b' ' * (json_length_aligned - json_length))

        f.write(struct.pack('<I', bin_length))
        f.write(struct.pack('<I', GLB_BIN_TYPE))
        f.write(spz_compressed)
        f.write(b'\x00' * (bin_length_aligned - bin_length))


def _write_glb_rgb_ply(file_path: str, data: SplatData):
    from ..core.morton import sort_morton
    from ..common.compress import compress_webp
    from ..common.codec import encode_spx_position_uint24

    sort_morton(data)
    count = data.count
    bs1, bs2, bs3, bs4 = bytearray(), bytearray(), bytearray(), bytearray()
    for i in range(count):
        bx = encode_spx_position_uint24(float(data.position[i, 0]))
        by = encode_spx_position_uint24(float(data.position[i, 1]))
        bz = encode_spx_position_uint24(float(data.position[i, 2]))
        bs1.extend([bx[0], by[0], bz[0], 255])
        bs2.extend([bx[1], by[1], bz[1], 255])
        bs3.extend([bx[2], by[2], bz[2], 255])
        bs4.extend([int(data.color[i, 0]), int(data.color[i, 1]), int(data.color[i, 2]), 255])

    bts = bytearray()
    cnt_bytes = struct.pack('<I', count)
    bts.extend([cnt_bytes[0], cnt_bytes[1], cnt_bytes[2], 255])
    bts.extend(bs1); bts.extend(bs2); bts.extend(bs3); bts.extend(bs4)
    webp_data = compress_webp(bytes(bts), quality=90)

    json_obj = {
        "asset": {"generator": f"pygsbox {VER}", "version": "2.0"},
        "bufferViews": [{"buffer": 0, "byteLength": len(webp_data)}],
        "buffers": [{"byteLength": len(webp_data)}],
        "extensions": {},
        "extensionsRequired": [
            "com_github_gotoeasy_gsbox",
            COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY
        ],
        "extensionsUsed": [
            "com_github_gotoeasy_gsbox",
            COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY
        ],
        "meshes": [{
            "primitives": [{
                "attributes": {},
                "extensions": {
                    "com_github_gotoeasy_gsbox": {
                        "extensions": {
                            COM_GITHUB_GOTOEASY_GSBOX_WEBP_RGB_PLY: {"bufferView": 0}
                        }
                    }
                },
                "mode": 0
            }]
        }],
        "nodes": [{"mesh": 0}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }

    json_str = json.dumps(json_obj)
    json_bytes = json_str.encode('utf-8')
    json_length = len(json_bytes)
    json_length_aligned = (json_length + 3) & ~3
    bin_length = len(webp_data)
    bin_length_aligned = (bin_length + 3) & ~3
    total_length = 12 + 8 + json_length_aligned + 8 + bin_length_aligned

    with open(file_path, 'wb') as f:
        f.write(GLB_MAGIC)
        f.write(struct.pack('<I', GLB_VERSION))
        f.write(struct.pack('<I', total_length))
        f.write(struct.pack('<I', json_length_aligned))
        f.write(struct.pack('<I', GLB_JSON_TYPE))
        f.write(json_bytes)
        f.write(b' ' * (json_length_aligned - json_length))
        f.write(struct.pack('<I', bin_length))
        f.write(struct.pack('<I', GLB_BIN_TYPE))
        f.write(webp_data)
        f.write(b'\x00' * (bin_length_aligned - bin_length))

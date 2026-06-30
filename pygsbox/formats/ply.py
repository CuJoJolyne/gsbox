import os
import math
import struct
import numpy as np
from typing import Tuple, List, Dict, Optional
from ..core.splat_data import SplatData
from ..common import codec


SQRT1_2 = 0.7071067811865476


class _CompressedChunk:
    __slots__ = ('min_x', 'min_y', 'min_z', 'max_x', 'max_y', 'max_z',
                 'min_scale_x', 'min_scale_y', 'min_scale_z',
                 'max_scale_x', 'max_scale_y', 'max_scale_z',
                 'min_r', 'min_g', 'min_b', 'max_r', 'max_g', 'max_b')
    def __init__(self):
        self.min_x = self.min_y = self.min_z = 0.0
        self.max_x = self.max_y = self.max_z = 0.0
        self.min_scale_x = self.min_scale_y = self.min_scale_z = 0.0
        self.max_scale_x = self.max_scale_y = self.max_scale_z = 0.0
        self.min_r = self.min_g = self.min_b = 0.0
        self.max_r = self.max_g = self.max_b = 0.0


class PlyHeader:
    def __init__(self):
        self.declare = ""
        self.format = ""
        self.comment = ""
        self.chunk_count = 0
        self.vertex_count = 0
        self.header_length = 0
        self.row_length = 0
        self.text = ""
        self.map_offset: Dict[str, int] = {}
        self.map_type: Dict[str, str] = {}

    def property(self, prop: str) -> Tuple[int, str]:
        return self.map_offset.get(prop, 0), self.map_type.get(prop, "")

    def max_sh_degree(self) -> int:
        if "f_rest_44" in self.map_type:
            return 3
        elif "f_rest_23" in self.map_type:
            return 2
        elif "f_rest_8" in self.map_type:
            return 1
        return 0

    def is_ply(self) -> bool:
        return self.text.startswith("ply\n")

    def get_comment(self) -> str:
        return self.comment

    def get_format(self) -> str:
        return self.format

    def to_string(self) -> str:
        return self.text

    def is_official_ply(self) -> bool:
        return (self.declare == "ply" and
                self.format == "binary_little_endian 1.0" and
                self.vertex_count > 0 and
                all(p in self.map_type for p in ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2",
                    "opacity", "scale_0", "scale_1", "scale_2",
                    "rot_0", "rot_1", "rot_2", "rot_3"]))

    def is_compressed_ply(self) -> bool:
        return (self.declare == "ply" and
                self.format == "binary_little_endian 1.0" and
                self.chunk_count > 0 and
                self.vertex_count > 0 and
                all(p in self.map_type for p in ["min_x", "min_y", "min_z", "max_x", "max_y", "max_z",
                    "min_scale_x", "min_scale_y", "min_scale_z", "max_scale_x", "max_scale_y", "max_scale_z",
                    "min_r", "min_g", "min_b", "max_r", "max_g", "max_b",
                    "packed_position", "packed_rotation", "packed_scale", "packed_color"]))

    def is_rgb_ply(self) -> bool:
        return (self.declare == "ply" and
                self.format == "binary_little_endian 1.0" and
                self.vertex_count > 0 and
                all(p in self.map_type for p in ["x", "y", "z", "red", "green", "blue"]))


def _get_type_size(name: str) -> int:
    sizes = {
        "float": 4, "double": 8, "int": 4, "uint": 4,
        "short": 2, "ushort": 2, "uchar": 1,
    }
    return sizes.get(name, 0)


def read_ply_header_string(file_path: str, read_len: int = 1024) -> str:
    """Read PLY header as string."""
    with open(file_path, 'rb') as f:
        bs = f.read(read_len)

    text = bs.decode('utf-8', errors='ignore')
    if "end_header\n" not in text:
        if read_len > 1024 * 10:
            raise ValueError("PLY header not found")
        return read_ply_header_string(file_path, read_len + 1024)

    header = text.split("end_header\n")[0] + "end_header\n"
    return header


def read_ply_header(file_path: str) -> PlyHeader:
    """Parse PLY header."""
    header_str = read_ply_header_string(file_path)
    header = PlyHeader()
    header.text = header_str
    header.header_length = len(header_str)

    lines = header_str.strip().split("\n")
    offset = 0
    vertex_count = -1
    chunk_count = 0

    for i, line in enumerate(lines):
        if i == 0:
            header.declare = line
        elif line.startswith("property "):
            parts = line.split(" ")
            if len(parts) >= 3:
                prop_name = parts[2]
                prop_type = parts[1]
                header.map_offset[prop_name] = offset
                header.map_type[prop_name] = prop_type
                offset += _get_type_size(prop_type)
        elif line.startswith("format "):
            header.format = line.replace("format ", "")
        elif line.startswith("element chunk "):
            chunk_count = int(line.replace("element chunk ", ""))
        elif line.startswith("element vertex "):
            vertex_count = int(line.replace("element vertex ", ""))
        elif line.startswith("comment "):
            header.comment = line.replace("comment ", "")

    header.vertex_count = vertex_count
    header.chunk_count = chunk_count
    header.row_length = offset
    return header


def read_ply(file_path: str) -> Tuple[PlyHeader, SplatData]:
    """Read PLY file."""
    header = read_ply_header(file_path)

    if header.is_compressed_ply():
        return header, _read_compressed_ply_data(file_path, header)
    elif header.is_official_ply():
        return header, _read_official_ply_data(file_path, header)
    elif header.is_rgb_ply():
        return header, _read_rgb_ply_data(file_path, header)
    else:
        raise ValueError("Unsupported PLY format")


def _read_official_ply_data(file_path: str, header: PlyHeader) -> SplatData:
    """Read standard 3DGS PLY data (vectorized)."""
    with open(file_path, 'rb') as f:
        f.seek(header.header_length)
        raw_data = f.read()

    count = header.vertex_count
    row_len = header.row_length

    # Build structured dtype from header property offsets
    fields = []
    for prop, off in header.map_offset.items():
        ptype = header.map_type[prop]
        np_type = _numpy_type(ptype)
        if off + np.dtype(np_type).itemsize <= row_len:
            fields.append((prop, np_type, off))

    fields.sort(key=lambda f: f[2])
    dtype = np.dtype({
        'names': [f[0] for f in fields],
        'formats': [f[1] for f in fields],
        'offsets': [f[2] for f in fields],
        'itemsize': row_len,
    })
    records = np.frombuffer(raw_data, dtype=dtype, count=count)

    data = SplatData(count)
    data.position[:, 0] = records['x'].astype(np.float32)
    data.position[:, 1] = records['y'].astype(np.float32) if 'y' in (dtype.names or ()) else 0.0
    data.position[:, 2] = records['z'].astype(np.float32)

    # Color: encode_splat_color(val) = clip_uint8((0.5 + SH_C0 * val) * 255)
    SH_C0 = codec.SH_C0
    data.color[:, 0] = np.clip(np.round((0.5 + SH_C0 * records['f_dc_0'].astype(np.float32)) * 255.0), 0, 255).astype(np.uint8)
    data.color[:, 1] = np.clip(np.round((0.5 + SH_C0 * records['f_dc_1'].astype(np.float32)) * 255.0), 0, 255).astype(np.uint8)
    data.color[:, 2] = np.clip(np.round((0.5 + SH_C0 * records['f_dc_2'].astype(np.float32)) * 255.0), 0, 255).astype(np.uint8)
    # Opacity: encode_splat_opacity(val) = clip_uint8(sigmoid(val) * 255)
    opacity_raw = records['opacity'].astype(np.float32)
    data.color[:, 3] = np.clip(np.round(1.0 / (1.0 + np.exp(-opacity_raw)) * 255.0), 0, 255).astype(np.uint8)

    # Scale: decode_splat_scale(val) = log(val)
    data.scale[:, 0] = np.log(records['scale_0'].astype(np.float32)).astype(np.float32)
    data.scale[:, 1] = np.log(records['scale_1'].astype(np.float32)).astype(np.float32)
    data.scale[:, 2] = np.log(records['scale_2'].astype(np.float32)).astype(np.float32)

    r0 = records['rot_0'].astype(np.float32)
    r1 = records['rot_1'].astype(np.float32)
    r2 = records['rot_2'].astype(np.float32)
    r3 = records['rot_3'].astype(np.float32)

    # Normalize rotations (vectorized)
    qlen = np.sqrt(r0 ** 2 + r1 ** 2 + r2 ** 2 + r3 ** 2)
    qlen = np.where(qlen > 0, qlen, np.float32(1.0))
    r0n, r1n, r2n, r3n = r0 / qlen, r1 / qlen, r2 / qlen, r3 / qlen
    data.rotation[:, 0] = np.clip(np.round(r0n * 128.0 + 128.0), 0, 255).astype(np.uint8)
    data.rotation[:, 1] = np.clip(np.round(r1n * 128.0 + 128.0), 0, 255).astype(np.uint8)
    data.rotation[:, 2] = np.clip(np.round(r2n * 128.0 + 128.0), 0, 255).astype(np.uint8)
    data.rotation[:, 3] = np.clip(np.round(r3n * 128.0 + 128.0), 0, 255).astype(np.uint8)

    # SH handling (vectorized)
    sh_degree = header.max_sh_degree()
    if sh_degree > 0:
        sh_count = {1: 9, 2: 24, 3: 45}.get(sh_degree, 0)
        sh_fields = []
        for sh_i in range(sh_count):
            prop = f'f_rest_{sh_i}'
            if prop in dtype.names:  # type: ignore[operator]
                sh_fields.append(prop)
        if sh_fields:
            sh_vals = np.column_stack([
                records[n].astype(np.float32) for n in sh_fields
            ])
            data.sh[:, :sh_count] = np.clip(
                np.round(sh_vals * 128.0) + 128, 0, 255
            ).astype(np.uint8)

    return data


def _normalize_rotations_f32(r0: float, r1: float, r2: float, r3: float) -> Tuple[int, int, int, int]:
    qlen = np.sqrt(r0 ** 2 + r1 ** 2 + r2 ** 2 + r3 ** 2)
    return (
        codec.clip_uint8((r0 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r1 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r2 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r3 / qlen) * 128.0 + 128.0),
    )


def _read_compressed_ply_data(file_path: str, header: PlyHeader) -> SplatData:
    chunk_count = header.chunk_count
    chunk_hdr_size = 18 * 4
    splat_size = 16

    chunks = _parse_compressed_chunks(file_path, header, chunk_count, chunk_hdr_size)
    data = _parse_compressed_splats(file_path, header, chunk_count, chunk_hdr_size, chunks, splat_size)
    _parse_compressed_sh(file_path, header, chunk_count, chunk_hdr_size, splat_size, data)
    return data


def _parse_compressed_chunks(file_path, header, chunk_count, chunk_hdr_size):
    chunks: List[_CompressedChunk] = []
    with open(file_path, 'rb') as f:
        f.seek(header.header_length)
        for _ in range(chunk_count):
            bs = f.read(chunk_hdr_size)
            ch = _CompressedChunk()
            ch.min_x = struct.unpack('<f', bs[0:4])[0]
            ch.min_y = struct.unpack('<f', bs[4:8])[0]
            ch.min_z = struct.unpack('<f', bs[8:12])[0]
            ch.max_x = struct.unpack('<f', bs[12:16])[0]
            ch.max_y = struct.unpack('<f', bs[16:20])[0]
            ch.max_z = struct.unpack('<f', bs[20:24])[0]
            ch.min_scale_x = struct.unpack('<f', bs[24:28])[0]
            ch.min_scale_y = struct.unpack('<f', bs[28:32])[0]
            ch.min_scale_z = struct.unpack('<f', bs[32:36])[0]
            ch.max_scale_x = struct.unpack('<f', bs[36:40])[0]
            ch.max_scale_y = struct.unpack('<f', bs[40:44])[0]
            ch.max_scale_z = struct.unpack('<f', bs[44:48])[0]
            ch.min_r = struct.unpack('<f', bs[48:52])[0]
            ch.min_g = struct.unpack('<f', bs[52:56])[0]
            ch.min_b = struct.unpack('<f', bs[56:60])[0]
            ch.max_r = struct.unpack('<f', bs[60:64])[0]
            ch.max_g = struct.unpack('<f', bs[64:68])[0]
            ch.max_b = struct.unpack('<f', bs[68:72])[0]
            chunks.append(ch)
    return chunks


def _parse_compressed_splats(file_path, header, chunk_count, chunk_hdr_size, chunks, splat_size):
    data = SplatData(header.vertex_count)
    base_offset = header.header_length + chunk_count * chunk_hdr_size
    n = 0
    with open(file_path, 'rb') as f:
        f.seek(base_offset)
        for i in range(chunk_count):
            ch = chunks[i]
            data_cnt = 256 if i < chunk_count - 1 else header.vertex_count % 256
            if data_cnt == 0:
                data_cnt = 256
            raw = f.read(data_cnt * splat_size)

            for j in range(data_cnt):
                boff = j * splat_size
                pk_pos = struct.unpack('<I', raw[boff:boff + 4])[0]
                pk_rot = struct.unpack('<I', raw[boff + 4:boff + 8])[0]
                pk_scl = struct.unpack('<I', raw[boff + 8:boff + 12])[0]
                pk_col = struct.unpack('<I', raw[boff + 12:boff + 16])[0]

                px, py, pz = _unpack_111011_xyz(pk_pos, ch)
                data.position[n] = (px, py, pz)

                data.rotation[n] = _unpack_rotations_compressed(pk_rot)

                sx, sy, sz = _unpack_111011_scale(pk_scl, ch)
                data.scale[n] = (sx, sy, sz)

                data.color[n] = _unpack_rgba_compressed(pk_col, ch)
                n += 1
    return data


def _unpack_111011_xyz(packed: int, ch: _CompressedChunk) -> tuple:
    x = float((packed >> 21) & 0x7FF) / 2047.0
    y = float((packed >> 11) & 0x3FF) / 1023.0
    z = float(packed & 0x7FF) / 2047.0
    return (
        codec.clip_float32(x * (ch.max_x - ch.min_x) + ch.min_x),
        codec.clip_float32(y * (ch.max_y - ch.min_y) + ch.min_y),
        codec.clip_float32(z * (ch.max_z - ch.min_z) + ch.min_z),
    )


def _unpack_111011_scale(packed: int, ch: _CompressedChunk) -> tuple:
    x = float((packed >> 21) & 0x7FF) / 2047.0
    y = float((packed >> 11) & 0x3FF) / 1023.0
    z = float(packed & 0x7FF) / 2047.0
    return (
        codec.clip_float32(x * (ch.max_scale_x - ch.min_scale_x) + ch.min_scale_x),
        codec.clip_float32(y * (ch.max_scale_y - ch.min_scale_y) + ch.min_scale_y),
        codec.clip_float32(z * (ch.max_scale_z - ch.min_scale_z) + ch.min_scale_z),
    )


def _unpack_rotations_compressed(packed: int) -> tuple:
    index = int(packed >> 30)
    remaining = packed
    max_val = 0x3FF
    sum_sq = 0.0
    rot = [0.0, 0.0, 0.0, 0.0]
    for i in [3, 2, 1, 0]:
        if i != index:
            mag = float(remaining & max_val) / float(max_val)
            rot[i] = (mag - 0.5) / SQRT1_2
            sum_sq += rot[i] * rot[i]
        remaining >>= 10
    rot[index] = math.sqrt(max(1.0 - sum_sq, 0.0))
    return (
        codec.clip_uint8(rot[0] * 128.0 + 128.0),
        codec.clip_uint8(rot[1] * 128.0 + 128.0),
        codec.clip_uint8(rot[2] * 128.0 + 128.0),
        codec.clip_uint8(rot[3] * 128.0 + 128.0),
    )


def _unpack_rgba_compressed(packed: int, ch: _CompressedChunk) -> tuple:
    rf = (float((packed >> 24) & 0xFF) / 255.0) * (ch.max_r - ch.min_r) + ch.min_r
    gf = (float((packed >> 16) & 0xFF) / 255.0) * (ch.max_g - ch.min_g) + ch.min_g
    bf = (float((packed >> 8) & 0xFF) / 255.0) * (ch.max_b - ch.min_b) + ch.min_b
    af = float(packed & 0xFF) / 255.0
    r = codec.encode_splat_color((rf - 0.5) / 0.28209479177387814)
    g = codec.encode_splat_color((gf - 0.5) / 0.28209479177387814)
    b = codec.encode_splat_color((bf - 0.5) / 0.28209479177387814)
    if af <= 0.0:
        a = 0
    elif af >= 1.0:
        a = 255
    else:
        a = codec.encode_splat_opacity(-math.log(1.0 / af - 1.0))
    return (r, g, b, a)


def _parse_compressed_sh(file_path, header, chunk_count, chunk_hdr_size, splat_size, data):
    sh_degree = header.max_sh_degree()
    sh_dims = {1: 3, 2: 8, 3: 15}
    sh_dim = sh_dims.get(sh_degree, 0)
    if sh_dim == 0:
        return
    sh_size = sh_dim * 3
    offset = header.header_length + chunk_count * chunk_hdr_size + header.vertex_count * splat_size
    with open(file_path, 'rb') as f:
        f.seek(offset)
        for i in range(header.vertex_count):
            sh_bytes = f.read(sh_size)
            n = 0
            for j in range(sh_dim):
                for c in range(3):
                    val = (float(sh_bytes[j + c * sh_dim]) / 256.0 - 0.5) * 8.0
                    data.sh[i, n] = codec.encode_splat_sh(val)
                    n += 1


def _read_rgb_ply_data(file_path: str, header: PlyHeader) -> SplatData:
    """Read RGB point cloud PLY data (x, y, z, red, green, blue as uchar)."""
    with open(file_path, 'rb') as f:
        f.seek(header.header_length)
        raw = f.read()

    count = header.vertex_count
    row_len = header.row_length
    if len(raw) < count * row_len:
        raise ValueError(
            f"RGB PLY: expected {count * row_len} bytes, got {len(raw)}"
        )

    # Build structured dtype based on property types
    dtype_fields = []
    for prop_name in ["x", "y", "z", "red", "green", "blue"]:
        off, ptype = header.property(prop_name)
        dtype_fields.append((prop_name, off, ptype))

    dtype = np.dtype([(n, _numpy_type(t)) for n, _, t in dtype_fields])
    arr = np.frombuffer(raw[:count * row_len], dtype=dtype).reshape(count)

    data = SplatData(count)
    data.position[:, 0] = arr["x"].astype(np.float32)
    data.position[:, 1] = arr["y"].astype(np.float32)
    data.position[:, 2] = arr["z"].astype(np.float32)
    data.color[:, 0] = arr["red"].astype(np.uint8)
    data.color[:, 1] = arr["green"].astype(np.uint8)
    data.color[:, 2] = arr["blue"].astype(np.uint8)
    data.color[:, 3] = 255
    data.scale[:, 0] = -4.6
    data.scale[:, 1] = -4.6
    data.scale[:, 2] = -4.6
    data.rotation[:, 0] = 255
    data.rotation[:, 1] = 128
    data.rotation[:, 2] = 128
    data.rotation[:, 3] = 128
    return data


def _numpy_type(ply_type: str):
    return {
        "float": np.float32, "double": np.float64,
        "int": np.int32, "uint": np.uint32,
        "short": np.int16, "ushort": np.uint16,
        "uchar": np.uint8,
    }[ply_type]


def write_ply(file_path: str, data: SplatData, comment: str = "", sh_degree: int = 0):
    """Write PLY file."""
    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

    has_sh = sh_degree > 0
    sh_count = {1: 9, 2: 24, 3: 45}.get(sh_degree, 0)

    header_lines = [
        "ply",
        "format binary_little_endian 1.0",
    ]
    if comment:
        header_lines.append(f"comment {comment}")
    header_lines.append(f"element vertex {data.count}")
    header_lines.append("property float x")
    header_lines.append("property float y")
    header_lines.append("property float z")
    header_lines.append("property float f_dc_0")
    header_lines.append("property float f_dc_1")
    header_lines.append("property float f_dc_2")

    if has_sh:
        for i in range(sh_count):
            header_lines.append(f"property float f_rest_{i}")

    header_lines.append("property float opacity")
    header_lines.append("property float scale_0")
    header_lines.append("property float scale_1")
    header_lines.append("property float scale_2")
    header_lines.append("property float rot_0")
    header_lines.append("property float rot_1")
    header_lines.append("property float rot_2")
    header_lines.append("property float rot_3")
    header_lines.append("end_header\n")

    header_bytes = "\n".join(header_lines).encode('utf-8')

    with open(file_path, 'wb') as f:
        f.write(header_bytes)

        for i in range(data.count):
            row = bytearray()

            row.extend(np.array([data.position[i, 0]], dtype=np.float32).tobytes())
            row.extend(np.array([data.position[i, 1]], dtype=np.float32).tobytes())
            row.extend(np.array([data.position[i, 2]], dtype=np.float32).tobytes())

            dc0 = codec.decode_splat_color(int(data.color[i, 0]))
            dc1 = codec.decode_splat_color(int(data.color[i, 1]))
            dc2 = codec.decode_splat_color(int(data.color[i, 2]))
            row.extend(np.array([dc0, dc1, dc2], dtype=np.float32).tobytes())

            if has_sh:
                sh_vals = []
                for sh_i in range(sh_count):
                    sh_vals.append(codec.decode_splat_sh(int(data.sh[i, sh_i])))
                row.extend(np.array(sh_vals, dtype=np.float32).tobytes())

            opacity = codec.decode_splat_opacity(int(data.color[i, 3]))
            row.extend(np.array([opacity], dtype=np.float32).tobytes())

            s0 = codec.encode_splat_scale(float(data.scale[i, 0]))
            s1 = codec.encode_splat_scale(float(data.scale[i, 1]))
            s2 = codec.encode_splat_scale(float(data.scale[i, 2]))
            row.extend(np.array([s0, s1, s2], dtype=np.float32).tobytes())

            r0 = codec.decode_splat_rotation(int(data.rotation[i, 0]))
            r1 = codec.decode_splat_rotation(int(data.rotation[i, 1]))
            r2 = codec.decode_splat_rotation(int(data.rotation[i, 2]))
            r3 = codec.decode_splat_rotation(int(data.rotation[i, 3]))
            row.extend(np.array([r0, r1, r2, r3], dtype=np.float32).tobytes())

            f.write(row)

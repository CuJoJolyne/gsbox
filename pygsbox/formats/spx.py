import os
import struct
import datetime
import numpy as np
from typing import Tuple, Optional, List
from ..core.splat_data import SplatData
from ..common import codec, compress

HEADER_SIZE_SPX = 128
NEWEST_SPX_VERSION = 3

BF_SPLAT22 = 22
BF_SPLAT23 = 23
BF_SPLAT220_WEBP = 220
BF_SPLAT230_WEBP = 230
BF_SH_PALETTES = 8
BF_SH_PALETTES_WEBP = 9

BF_SPLAT19 = 19
BF_SPLAT20 = 20
BF_SPLAT190_WEBP = 190
BF_SPLAT10019 = 10019
BF_SPLAT10190_WEBP = 10190
BF_SH1 = 1
BF_SH2 = 2
BF_SH3 = 3
BF_SH3_WEBP = 4

CT_GZIP = 0
CT_XZ = 1

DEFAULT_BLOCK_SIZE = 102400
MAX_BLOCK_SIZE = 16000000
MIN_BLOCK_SIZE = 4096
MIN_WEBP_BLOCK_SIZE = 4096

BLOCK_HEADER_SIZE = 4
BLOCK_INFO_SIZE = 8
PALETTE_ENTRY_SIZE = 60
SH_BANDS_TOTAL = 45
SH_PALETTE_BAND_COUNT = 15


class SpxHeader:
    def __init__(self):
        self.fixed: str = "spx"
        self.version: int = 0
        self.splat_count: int = 0
        self.min_x: float = 0.0
        self.max_x: float = 0.0
        self.min_y: float = 0.0
        self.max_y: float = 0.0
        self.min_z: float = 0.0
        self.max_z: float = 0.0
        self.min_top_y: float = 0.0
        self.max_top_y: float = 0.0
        self.create_date: int = 0
        self.creater_id: int = 0
        self.exclusive_id: int = 0
        self.sh_degree: int = 0
        self.flags: int = 0
        self.lod: int = 0
        self.reserve3: int = 0
        self.comment: str = ""
        self.hash_val: int = 0
        self.check_hash: bool = False
        self.palettes: List[int] = []

    def is_inverted(self) -> bool:
        return (self.flags & 0x80) > 0

    def is_large_scene(self) -> bool:
        return (self.flags & 0x01) > 0

    def is_valid(self) -> bool:
        return self.check_hash

    def to_string(self) -> str:
        return (
            f"SpxHeader(version={self.version}, splat_count={self.splat_count}, "
            f"sh_degree={self.sh_degree}, flags={self.flags}, lod={self.lod}, "
            f"bounds=({self.min_x:.2f},{self.max_x:.2f}),({self.min_y:.2f},{self.max_y:.2f}),"
            f"({self.min_z:.2f},{self.max_z:.2f}), comment='{self.comment}')"
        )


def parse_spx_header(file_path: str) -> SpxHeader:
    with open(file_path, 'rb') as f:
        bs = f.read(HEADER_SIZE_SPX)

    if len(bs) < HEADER_SIZE_SPX:
        raise ValueError("File too small for SPX header")

    if bs[0] != ord('s') or bs[1] != ord('p') or bs[2] != ord('x'):
        raise ValueError("Invalid SPX magic bytes")

    spx_ver = bs[3]
    if spx_ver < 1 or spx_ver > NEWEST_SPX_VERSION:
        raise ValueError(f"Unsupported SPX version: {spx_ver}")

    header = SpxHeader()
    header.version = spx_ver
    header.splat_count = struct.unpack('<i', bs[4:8])[0]
    header.min_x = struct.unpack('<f', bs[8:12])[0]
    header.max_x = struct.unpack('<f', bs[12:16])[0]
    header.min_y = struct.unpack('<f', bs[16:20])[0]
    header.max_y = struct.unpack('<f', bs[20:24])[0]
    header.min_z = struct.unpack('<f', bs[24:28])[0]
    header.max_z = struct.unpack('<f', bs[28:32])[0]
    header.min_top_y = struct.unpack('<f', bs[32:36])[0]
    header.max_top_y = struct.unpack('<f', bs[36:40])[0]
    header.create_date = struct.unpack('<I', bs[40:44])[0]
    header.creater_id = struct.unpack('<I', bs[44:48])[0]
    header.exclusive_id = struct.unpack('<I', bs[48:52])[0]
    header.sh_degree = bs[52]

    if spx_ver >= 2:
        header.flags = bs[53]
        header.lod = bs[54]
        header.reserve3 = bs[55]

    if header.sh_degree not in (1, 2, 3):
        header.sh_degree = 0

    header.comment = bs[64:124].decode('utf-8', errors='ignore').rstrip('\x00').strip()
    header.hash_val = struct.unpack('<I', bs[124:128])[0]
    header.check_hash = codec.hash_bytes(bs[0:124]) == header.hash_val

    return header


def gen_spx_header_v3(data: SplatData, comment: str, sh_degree: int) -> SpxHeader:
    header = SpxHeader()
    header.version = 3
    header.splat_count = data.count

    if data.count > 0:
        header.min_x = float(np.min(data.position[:, 0]))
        header.max_x = float(np.max(data.position[:, 0]))
        header.min_y = float(np.min(data.position[:, 1]))
        header.max_y = float(np.max(data.position[:, 1]))
        header.min_z = float(np.min(data.position[:, 2]))
        header.max_z = float(np.max(data.position[:, 2]))

    header.min_top_y = header.min_y
    header.max_top_y = header.max_y

    now = datetime.date.today()
    header.create_date = now.year * 10000 + now.month * 100 + now.day
    header.creater_id = 1202056903
    header.exclusive_id = 0
    header.sh_degree = sh_degree
    header.flags = 0
    header.lod = 0
    header.reserve3 = 0
    header.comment = comment

    return header


def spx_header_to_bytes(header: SpxHeader) -> bytes:
    result = bytearray(128)

    result[0:3] = b'spx'
    result[3] = header.version
    struct.pack_into('<i', result, 4, header.splat_count)
    struct.pack_into('<f', result, 8, header.min_x)
    struct.pack_into('<f', result, 12, header.max_x)
    struct.pack_into('<f', result, 16, header.min_y)
    struct.pack_into('<f', result, 20, header.max_y)
    struct.pack_into('<f', result, 24, header.min_z)
    struct.pack_into('<f', result, 28, header.max_z)
    struct.pack_into('<f', result, 32, header.min_top_y)
    struct.pack_into('<f', result, 36, header.max_top_y)
    struct.pack_into('<I', result, 40, header.create_date)
    struct.pack_into('<I', result, 44, header.creater_id)
    struct.pack_into('<I', result, 48, header.exclusive_id)
    result[52] = header.sh_degree
    result[53] = header.flags
    result[54] = header.lod
    result[55] = header.reserve3
    struct.pack_into('<I', result, 56, 0)
    struct.pack_into('<I', result, 60, 0)

    comment_bytes = header.comment.encode('utf-8', errors='ignore')[:60].ljust(60, b'\x00')
    result[64:124] = comment_bytes

    hash_val = codec.hash_bytes(bytes(result[0:124]))
    struct.pack_into('<I', result, 124, hash_val)

    return bytes(result)


def read_spx(file_path: str) -> Tuple[SpxHeader, SplatData]:
    header = parse_spx_header(file_path)

    if header.version == 1:
        data = _read_spx_v1(file_path, header)
    elif header.version == 2:
        data = _read_spx_v2(file_path, header)
    elif header.version == 3:
        data = _read_spx_v3(file_path, header)
    else:
        raise ValueError(f"Unsupported SPX version: {header.version}")

    return header, data


def _read_spx_v1(file_path: str, header: SpxHeader) -> SplatData:
    data = SplatData(0)
    n1 = n2 = n3 = 0

    with open(file_path, 'rb') as f:
        f.seek(HEADER_SIZE_SPX)
        while True:
            raw = f.read(BLOCK_HEADER_SIZE)
            if len(raw) < BLOCK_HEADER_SIZE:
                break
            encoded_size = struct.unpack('<i', raw)[0]
            if encoded_size < 0:
                size = -encoded_size
                block_raw = compress.decompress_gzip(f.read(size))
            else:
                block_raw = f.read(encoded_size)
            if len(block_raw) < BLOCK_INFO_SIZE:
                break
            count = struct.unpack('<I', block_raw[0:4])[0]
            fmt_id = struct.unpack('<I', block_raw[4:8])[0]
            payload = block_raw[BLOCK_INFO_SIZE:]

            if fmt_id == BF_SPLAT20:
                bd = _read_spx_v1_splat20(payload, count)
                data.append(bd)
            elif fmt_id == BF_SH1:
                _apply_sh_block(data, payload, count, n1, 9)
                n1 += count
            elif fmt_id == BF_SH2:
                _apply_sh_block(data, payload, count, n2, 24)
                n2 += count
            elif fmt_id == BF_SH3:
                _apply_sh_block(data, payload, count, n3, 21, dst_offset=24)
                n3 += count
    return data


def _read_spx_v1_splat20(payload: bytes, count: int) -> SplatData:
    import math
    pos_size = count * 3
    data = SplatData(count)
    for i in range(count):
        data.position[i, 0] = codec.decode_spx_position_uint24(
            payload[i * 3], payload[i * 3 + 1], payload[i * 3 + 2])
        data.position[i, 1] = codec.decode_spx_position_uint24(
            payload[pos_size + i * 3], payload[pos_size + i * 3 + 1], payload[pos_size + i * 3 + 2])
        data.position[i, 2] = codec.decode_spx_position_uint24(
            payload[pos_size * 2 + i * 3], payload[pos_size * 2 + i * 3 + 1], payload[pos_size * 2 + i * 3 + 2])
        data.scale[i, 0] = codec.decode_spx_scale(payload[pos_size * 3 + i])
        data.scale[i, 1] = codec.decode_spx_scale(payload[pos_size * 3 + count + i])
        data.scale[i, 2] = codec.decode_spx_scale(payload[pos_size * 3 + count * 2 + i])
        data.color[i, 0] = payload[pos_size * 3 + count * 3 + i]
        data.color[i, 1] = payload[pos_size * 3 + count * 4 + i]
        data.color[i, 2] = payload[pos_size * 3 + count * 5 + i]
        data.color[i, 3] = payload[pos_size * 3 + count * 6 + i]
        rw = payload[pos_size * 3 + count * 7 + i]
        rx = payload[pos_size * 3 + count * 8 + i]
        ry = payload[pos_size * 3 + count * 9 + i]
        rz = payload[pos_size * 3 + count * 10 + i]
        r0 = rw / 128.0 - 1.0; r1 = rx / 128.0 - 1.0
        r2 = ry / 128.0 - 1.0; r3 = rz / 128.0 - 1.0
        qlen = math.sqrt(r0 * r0 + r1 * r1 + r2 * r2 + r3 * r3)
        if qlen > 0:
            r0 /= qlen; r1 /= qlen; r2 /= qlen; r3 /= qlen
        data.rotation[i, 0] = codec.clip_uint8(r0 * 128.0 + 128.0)
        data.rotation[i, 1] = codec.clip_uint8(r1 * 128.0 + 128.0)
        data.rotation[i, 2] = codec.clip_uint8(r2 * 128.0 + 128.0)
        data.rotation[i, 3] = codec.clip_uint8(r3 * 128.0 + 128.0)
    return data


def _apply_sh_block(data, payload, count, offset, sh_size, dst_offset=0):
    for n in range(count):
        idx = offset + n
        if idx >= data.count:
            continue
        for j in range(sh_size):
            data.sh[idx, dst_offset + j] = payload[n * sh_size + j]


def _read_spx_v2(file_path: str, header: SpxHeader) -> SplatData:
    data = SplatData(0)
    n1 = n2 = n3 = 0

    with open(file_path, 'rb') as f:
        f.seek(HEADER_SIZE_SPX)
        while True:
            raw = f.read(BLOCK_HEADER_SIZE)
            if len(raw) < BLOCK_HEADER_SIZE:
                break
            encoded_size = struct.unpack('<i', raw)[0]
            if encoded_size < 0:
                raw_encoded_size = -encoded_size
                compress_type = (raw_encoded_size >> 28) & 0x7
                compressed_size = raw_encoded_size & 0x0FFFFFFF
                block_raw = _decompress_block_data(f, compressed_size, compress_type)
            else:
                block_raw = f.read(encoded_size)
            if len(block_raw) < BLOCK_INFO_SIZE:
                break
            count = struct.unpack('<I', block_raw[0:4])[0]
            fmt_id = struct.unpack('<I', block_raw[4:8])[0]
            payload = block_raw[BLOCK_INFO_SIZE:]

            if fmt_id == BF_SPLAT19:
                data.append(_read_spx_v2_splat19(payload, count))
            elif fmt_id == BF_SPLAT10019:
                data.append(_read_spx_v2_splat10019(payload, count))
            elif fmt_id == BF_SPLAT190_WEBP:
                data.append(_read_spx_v2_webp190(payload, count))
            elif fmt_id == BF_SPLAT10190_WEBP:
                data.append(_read_spx_v2_webp10190(payload, count))
            elif fmt_id == BF_SPLAT20:
                data.append(_read_spx_v1_splat20(payload, count))
            elif fmt_id == BF_SH1:
                _apply_sh_block(data, payload, count, n1, 9); n1 += count
            elif fmt_id == BF_SH2:
                _apply_sh_block(data, payload, count, n2, 24); n2 += count
            elif fmt_id == BF_SH3:
                _apply_sh_block(data, payload, count, n3, 21, dst_offset=24); n3 += count
            elif fmt_id == BF_SH3_WEBP:
                _read_spx_v2_sh3_webp(data, payload, count, n3); n3 += count
    return data


def _read_spx_v2_splat19(payload: bytes, count: int) -> SplatData:
    data = SplatData(count)
    for i in range(count):
        data.position[i, 0] = codec.decode_spx_position_uint24(
            payload[i], payload[count * 3 + i], payload[count * 6 + i])
        data.position[i, 1] = codec.decode_spx_position_uint24(
            payload[count + i], payload[count * 4 + i], payload[count * 7 + i])
        data.position[i, 2] = codec.decode_spx_position_uint24(
            payload[count * 2 + i], payload[count * 5 + i], payload[count * 8 + i])
        data.scale[i, 0] = codec.decode_spx_scale(payload[count * 9 + i])
        data.scale[i, 1] = codec.decode_spx_scale(payload[count * 10 + i])
        data.scale[i, 2] = codec.decode_spx_scale(payload[count * 11 + i])
        data.color[i, 0] = payload[count * 12 + i]
        data.color[i, 1] = payload[count * 13 + i]
        data.color[i, 2] = payload[count * 14 + i]
        data.color[i, 3] = payload[count * 15 + i]
        rw, rx, ry, rz = codec.decode_spx_rotations(
            payload[count * 16 + i], payload[count * 17 + i], payload[count * 18 + i])
        data.rotation[i, 0] = rw
        data.rotation[i, 1] = rx
        data.rotation[i, 2] = ry
        data.rotation[i, 3] = rz
    return data


def _read_spx_v2_splat10019(payload: bytes, count: int) -> SplatData:
    log_times = payload[0]
    payload = payload[4:]
    data = SplatData(count)
    for i in range(count):
        x = codec.decode_spx_position_uint24(
            payload[i], payload[count * 3 + i], payload[count * 6 + i])
        y = codec.decode_spx_position_uint24(
            payload[count + i], payload[count * 4 + i], payload[count * 7 + i])
        z = codec.decode_spx_position_uint24(
            payload[count * 2 + i], payload[count * 5 + i], payload[count * 8 + i])
        data.position[i, 0] = codec.decode_log(x, log_times)
        data.position[i, 1] = codec.decode_log(y, log_times)
        data.position[i, 2] = codec.decode_log(z, log_times)
        data.scale[i, 0] = codec.decode_spx_scale(payload[count * 9 + i])
        data.scale[i, 1] = codec.decode_spx_scale(payload[count * 10 + i])
        data.scale[i, 2] = codec.decode_spx_scale(payload[count * 11 + i])
        data.color[i, 0] = payload[count * 12 + i]
        data.color[i, 1] = payload[count * 13 + i]
        data.color[i, 2] = payload[count * 14 + i]
        data.color[i, 3] = payload[count * 15 + i]
        rw, rx, ry, rz = codec.decode_spx_rotations(
            payload[count * 16 + i], payload[count * 17 + i], payload[count * 18 + i])
        data.rotation[i, 0] = rw
        data.rotation[i, 1] = rx
        data.rotation[i, 2] = ry
        data.rotation[i, 3] = rz
    return data


def _read_spx_v2_webp190(payload: bytes, count: int) -> SplatData:
    offset = 0
    def read_webp():
        nonlocal offset
        if offset + 4 > len(payload):
            return b''
        sz = struct.unpack('<I', payload[offset:offset + 4])[0]
        offset += 4
        if offset + sz > len(payload):
            return b''
        webp_data = payload[offset:offset + sz]
        offset += sz
        raw, _, _ = compress.decompress_webp(webp_data)
        return bytes(raw)

    pos_img = read_webp()
    sc_img = read_webp()
    c_img = read_webp()
    r_img = read_webp()

    data = SplatData(count)
    for i in range(count):
        x0 = pos_img[i * 4 + 0]; y0 = pos_img[i * 4 + 1]; z0 = pos_img[i * 4 + 2]
        x1 = pos_img[count * 4 + i * 4 + 0]; y1 = pos_img[count * 4 + i * 4 + 1]; z1 = pos_img[count * 4 + i * 4 + 2]
        x2 = pos_img[count * 8 + i * 4 + 0]; y2 = pos_img[count * 8 + i * 4 + 1]; z2 = pos_img[count * 8 + i * 4 + 2]
        data.position[i, 0] = codec.decode_spx_position_uint24(x0, x1, x2)
        data.position[i, 1] = codec.decode_spx_position_uint24(y0, y1, y2)
        data.position[i, 2] = codec.decode_spx_position_uint24(z0, z1, z2)
        data.scale[i, 0] = codec.decode_spx_scale(sc_img[i * 4 + 0])
        data.scale[i, 1] = codec.decode_spx_scale(sc_img[i * 4 + 1])
        data.scale[i, 2] = codec.decode_spx_scale(sc_img[i * 4 + 2])
        data.color[i, 0] = c_img[i * 4 + 0]
        data.color[i, 1] = c_img[i * 4 + 1]
        data.color[i, 2] = c_img[i * 4 + 2]
        data.color[i, 3] = c_img[i * 4 + 3]
        rw, rx, ry, rz = codec.decode_spx_rotations(
            r_img[i * 4 + 0], r_img[i * 4 + 1], r_img[i * 4 + 2])
        data.rotation[i, 0] = rw
        data.rotation[i, 1] = rx
        data.rotation[i, 2] = ry
        data.rotation[i, 3] = rz
    return data


def _read_spx_v2_webp10190(payload: bytes, count: int) -> SplatData:
    log_times = payload[0] if len(payload) > 0 else 0
    payload = payload[4:]
    offset = 0
    def read_webp():
        nonlocal offset
        sz = struct.unpack('<I', payload[offset:offset + 4])[0]
        offset += 4
        webp_data = payload[offset:offset + sz]
        offset += sz
        raw, _, _ = compress.decompress_webp(webp_data)
        return bytes(raw)

    pos_img = read_webp()
    sc_img = read_webp()
    c_img = read_webp()
    r_img = read_webp()

    data = SplatData(count)
    for i in range(count):
        x0 = pos_img[i * 4 + 0]; y0 = pos_img[i * 4 + 1]; z0 = pos_img[i * 4 + 2]
        x1 = pos_img[count * 4 + i * 4 + 0]; y1 = pos_img[count * 4 + i * 4 + 1]; z1 = pos_img[count * 4 + i * 4 + 2]
        x2 = pos_img[count * 8 + i * 4 + 0]; y2 = pos_img[count * 8 + i * 4 + 1]; z2 = pos_img[count * 8 + i * 4 + 2]
        data.position[i, 0] = codec.decode_log(
            codec.decode_spx_position_uint24(x0, x1, x2), log_times)
        data.position[i, 1] = codec.decode_log(
            codec.decode_spx_position_uint24(y0, y1, y2), log_times)
        data.position[i, 2] = codec.decode_log(
            codec.decode_spx_position_uint24(z0, z1, z2), log_times)
        data.scale[i, 0] = codec.decode_spx_scale(sc_img[i * 4 + 0])
        data.scale[i, 1] = codec.decode_spx_scale(sc_img[i * 4 + 1])
        data.scale[i, 2] = codec.decode_spx_scale(sc_img[i * 4 + 2])
        data.color[i, 0] = c_img[i * 4 + 0]
        data.color[i, 1] = c_img[i * 4 + 1]
        data.color[i, 2] = c_img[i * 4 + 2]
        data.color[i, 3] = c_img[i * 4 + 3]
        rw, rx, ry, rz = codec.decode_spx_rotations(
            r_img[i * 4 + 0], r_img[i * 4 + 1], r_img[i * 4 + 2])
        data.rotation[i, 0] = rw
        data.rotation[i, 1] = rx
        data.rotation[i, 2] = ry
        data.rotation[i, 3] = rz
    return data


def _read_spx_v2_sh3_webp(data, payload, count, offset):
    rgba, _, _ = compress.decompress_webp(payload)
    for n in range(count):
        idx = offset + n
        if idx >= data.count:
            continue
        for b in range(15):
            data.sh[idx, b * 3 + 0] = rgba[n * 15 * 4 + b * 4 + 0]
            data.sh[idx, b * 3 + 1] = rgba[n * 15 * 4 + b * 4 + 1]
            data.sh[idx, b * 3 + 2] = rgba[n * 15 * 4 + b * 4 + 2]


def _read_spx_v3(file_path: str, header: SpxHeader) -> SplatData:
    data = SplatData(0)
    palettes: List[int] = []

    with open(file_path, 'rb') as f:
        f.seek(HEADER_SIZE_SPX)

        while True:
            block_header_bytes = f.read(BLOCK_HEADER_SIZE)
            if len(block_header_bytes) < BLOCK_HEADER_SIZE:
                break

            encoded_size = struct.unpack('<i', block_header_bytes)[0]

            if encoded_size < 0:
                raw_encoded_size = -encoded_size
                compress_type = (raw_encoded_size >> 28) & 0x7
                compressed_size = raw_encoded_size & 0x0FFFFFFF
                raw_data = _decompress_block_data(f, compressed_size, compress_type)
            else:
                raw_data = f.read(encoded_size)

            if len(raw_data) < BLOCK_INFO_SIZE:
                break

            count = struct.unpack('<I', raw_data[0:4])[0]
            format_id = struct.unpack('<I', raw_data[4:8])[0]
            payload = raw_data[BLOCK_INFO_SIZE:]

            if format_id in (BF_SPLAT22, BF_SPLAT23):
                block_data = _read_spx_v3_block(payload, count, format_id)
                data.append(block_data)
            elif format_id in (BF_SPLAT220_WEBP, BF_SPLAT230_WEBP):
                block_data = _read_spx_webp_v3_block(payload, count, format_id)
                data.append(block_data)
            elif format_id == BF_SH_PALETTES:
                palettes = _read_palettes_block(payload)
            elif format_id == BF_SH_PALETTES_WEBP:
                palettes = _read_palettes_webp_block(payload)

    if palettes and header.sh_degree > 0:
        _set_sh_by_palettes(data, palettes)

    return data


def _decompress_block_data(f, size: int, compress_type: int) -> bytes:
    compressed = f.read(size)
    if compress_type == CT_GZIP:
        return compress.decompress_gzip(compressed)
    elif compress_type == CT_XZ:
        return compress.decompress_xz(compressed)
    else:
        raise ValueError(f"Unknown compression type: {compress_type}")


def _read_spx_v3_block(payload: bytes, count: int, format_id: int) -> SplatData:
    channels = _decode_channels_from_interleaved(payload, count)
    return _decode_splat_from_channels(channels, count)


def _read_spx_webp_v3_block(payload: bytes, count: int, format_id: int) -> SplatData:
    offset = 0

    def read_webp_channel() -> bytes:
        nonlocal offset
        if offset + 4 > len(payload):
            return b''
        size = struct.unpack('<I', payload[offset:offset + 4])[0]
        offset += 4
        if offset + size > len(payload):
            return b''
        webp_data = payload[offset:offset + size]
        offset += size
        raw, w, h = compress.decompress_webp(webp_data)
        return bytes(raw)

    pos_img0 = read_webp_channel()
    pos_img1 = read_webp_channel()
    pos_img2 = read_webp_channel()
    scale_img = read_webp_channel()
    color_img = read_webp_channel()
    rot_img = read_webp_channel()
    palette_img = read_webp_channel()
    flag_img = read_webp_channel()

    ch0 = _extract_pos_channel_from_image(pos_img0, count, 0)
    ch1 = _extract_pos_channel_from_image(pos_img1, count, 1)
    ch2 = _extract_pos_channel_from_image(pos_img2, count, 2)

    scale_raw = np.frombuffer(scale_img, dtype=np.uint8)[:count * 4].reshape(-1, 4)
    ch3 = np.zeros(count * 3, dtype=np.uint8)
    n = min(len(scale_raw), count)
    if n > 0:
        ch3[0::3] = scale_raw[:n, 0]
        ch3[1::3] = scale_raw[:n, 1]
        ch3[2::3] = scale_raw[:n, 2]

    color_raw = np.frombuffer(color_img, dtype=np.uint8)
    ch4 = np.zeros(count * 4, dtype=np.uint8)
    ch4[:min(len(color_raw), count * 4)] = color_raw[:min(len(color_raw), count * 4)]

    rot_raw = np.frombuffer(rot_img, dtype=np.uint8)[:count * 4].reshape(-1, 4)
    ch5 = np.zeros(count * 4, dtype=np.uint8)
    rn = min(len(rot_raw), count)
    if rn > 0:
        rw_arr, rx_arr, ry_arr, rz_arr = [], [], [], []
        for i in range(rn):
            r0, r1, r2, ri = int(rot_raw[i, 0]), int(rot_raw[i, 1]), int(rot_raw[i, 2]), int(rot_raw[i, 3])
            rr0, rr1, rr2, rr3 = codec.sog_decode_rotations(r0, r1, r2, ri)
            rw_arr.append(rr0)
            rx_arr.append(rr1)
            ry_arr.append(rr2)
            rz_arr.append(rr3)
        ch5[0::4] = rw_arr
        ch5[1::4] = rx_arr
        ch5[2::4] = ry_arr
        ch5[3::4] = rz_arr

    pal_raw = np.frombuffer(palette_img, dtype=np.uint8)[:count * 4].reshape(-1, 4)
    ch6 = np.zeros(count * 2, dtype=np.uint8)
    pn = min(len(pal_raw), count)
    if pn > 0:
        ch6[0::2] = pal_raw[:pn, 0]
        ch6[1::2] = pal_raw[:pn, 1]

    flag_raw = np.frombuffer(flag_img, dtype=np.uint8)
    ch7 = np.zeros(count * 2, dtype=np.uint8)
    ch7[:min(len(flag_raw), count * 2)] = flag_raw[:min(len(flag_raw), count * 2)]

    channels = [ch0, ch1, ch2, ch3, ch4, ch5, ch6, ch7]
    return _decode_splat_from_channels(channels, count)


def _extract_pos_channel_from_image(img_data: bytes, count: int, byte_idx: int) -> np.ndarray:
    ch = np.zeros(count * 3, dtype=np.uint8)
    raw = np.frombuffer(img_data, dtype=np.uint8)[:count * 4].reshape(-1, 4)
    n = min(len(raw), count)
    if n > 0:
        for ax in range(3):
            ch[ax::3] = raw[:n, ax]
    return ch


def _decode_channels_from_interleaved(payload: bytes, count: int) -> List[np.ndarray]:
    ch0 = np.zeros(count * 3, dtype=np.uint8)
    ch1 = np.zeros(count * 3, dtype=np.uint8)
    ch2 = np.zeros(count * 3, dtype=np.uint8)
    ch3 = np.zeros(count * 3, dtype=np.uint8)
    ch4 = np.zeros(count * 4, dtype=np.uint8)
    ch5 = np.zeros(count * 4, dtype=np.uint8)
    ch6 = np.zeros(count * 2, dtype=np.uint8)
    ch7 = np.zeros(count * 2, dtype=np.uint8)

    idx = 0

    for byte_idx in range(3):
        for axis in range(3):
            for i in range(count):
                if idx < len(payload):
                    val = payload[idx]
                    idx += 1
                    if axis == 0:
                        ch0[i * 3 + byte_idx] = val
                    elif axis == 1:
                        ch1[i * 3 + byte_idx] = val
                    else:
                        ch2[i * 3 + byte_idx] = val

    for axis in range(3):
        for i in range(count):
            if idx < len(payload):
                ch3[i * 3 + axis] = payload[idx]
                idx += 1

    for comp in range(4):
        for i in range(count):
            if idx < len(payload):
                ch4[i * 4 + comp] = payload[idx]
                idx += 1

    for comp in range(4):
        for i in range(count):
            if idx < len(payload):
                ch5[i * 4 + comp] = payload[idx]
                idx += 1

    for comp in range(2):
        for i in range(count):
            if idx < len(payload):
                ch6[i * 2 + comp] = payload[idx]
                idx += 1

    for comp in range(2):
        for i in range(count):
            if idx < len(payload):
                ch7[i * 2 + comp] = payload[idx]
                idx += 1

    return [ch0, ch1, ch2, ch3, ch4, ch5, ch6, ch7]


def _decode_splat_from_channels(channels: List[np.ndarray], count: int) -> SplatData:
    data = SplatData(count)

    ch0, ch1, ch2 = channels[0], channels[1], channels[2]
    ch3 = channels[3]
    ch4, ch5, ch6 = channels[4], channels[5], channels[6]
    ch7 = channels[7] if len(channels) > 7 else np.zeros(count * 2, dtype=np.uint8)

    for i in range(count):
        x = codec.decode_spx_position_uint24(
            int(ch0[i * 3 + 0]), int(ch1[i * 3 + 0]), int(ch2[i * 3 + 0])
        )
        y = codec.decode_spx_position_uint24(
            int(ch0[i * 3 + 1]), int(ch1[i * 3 + 1]), int(ch2[i * 3 + 1])
        )
        z = codec.decode_spx_position_uint24(
            int(ch0[i * 3 + 2]), int(ch1[i * 3 + 2]), int(ch2[i * 3 + 2])
        )
        data.position[i, 0] = x
        data.position[i, 1] = y
        data.position[i, 2] = z

        data.scale[i, 0] = codec.decode_spx_scale(int(ch3[i * 3 + 0]))
        data.scale[i, 1] = codec.decode_spx_scale(int(ch3[i * 3 + 1]))
        data.scale[i, 2] = codec.decode_spx_scale(int(ch3[i * 3 + 2]))

        data.color[i, 0] = int(ch4[i * 4 + 0])
        data.color[i, 1] = int(ch4[i * 4 + 1])
        data.color[i, 2] = int(ch4[i * 4 + 2])
        data.color[i, 3] = int(ch4[i * 4 + 3])

        rw, rx, ry, rz = codec.decode_spx_rotations(
            int(ch5[i * 4 + 1]), int(ch5[i * 4 + 2]), int(ch5[i * 4 + 3])
        )
        data.rotation[i, 0] = rw
        data.rotation[i, 1] = rx
        data.rotation[i, 2] = ry
        data.rotation[i, 3] = rz

        data.palette_idx[i] = int(ch6[i * 2 + 0]) | (int(ch6[i * 2 + 1]) << 8)
        data.flag_value[i] = int(ch7[i * 2 + 0]) | (int(ch7[i * 2 + 1]) << 8)

    return data


def _read_palettes_block(payload: bytes) -> List[int]:
    palettes: List[int] = []
    for i in range(0, len(payload), PALETTE_ENTRY_SIZE):
        if i + PALETTE_ENTRY_SIZE <= len(payload):
            vals = list(payload[i:i + PALETTE_ENTRY_SIZE])
            palettes.extend(vals)
    return palettes


def _read_palettes_webp_block(payload: bytes) -> List[int]:
    raw, w, h = compress.decompress_webp(payload)
    return list(raw[:h * w * 4])


def _set_sh_by_palettes(data: SplatData, palettes: List[int]):
    palette_count = len(palettes) // PALETTE_ENTRY_SIZE
    if palette_count == 0:
        return

    bands = min(SH_BANDS_TOTAL, data.sh.shape[1]) if data.sh.size > 0 else SH_BANDS_TOTAL

    for i in range(data.count):
        pid = int(data.palette_idx[i])
        if pid < 0 or pid >= palette_count:
            continue
        offset = pid * PALETTE_ENTRY_SIZE
        for b in range(bands):
            src_base = offset + b * 4
            if src_base + 3 <= len(palettes):
                data.sh[i, b] = (palettes[src_base] ^ palettes[src_base + 1]) & 0xFF


def write_spx(
    file_path: str,
    data: SplatData,
    comment: str = "",
    sh_degree: int = 0,
    block_size: int = DEFAULT_BLOCK_SIZE,
    block_format: int = BF_SPLAT220_WEBP,
    quality: int = 90,
    version: int = 3,
):
    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

    if version == 1:
        _write_spx_v1(file_path, data, comment, sh_degree, block_size)
    elif version == 2:
        _write_spx_v2(file_path, data, comment, sh_degree, block_size, block_format, quality)
    else:
        _write_spx_v3_write(file_path, data, comment, sh_degree, block_size, block_format, quality)


def _write_spx_v1(file_path, data, comment, sh_degree, block_size):
    header = gen_spx_header_v3(data, comment, sh_degree)
    header.version = 1
    header_bytes = spx_header_to_bytes(header)
    with open(file_path, 'wb') as f:
        f.write(header_bytes)
        blocks = _build_blocks(data.count, block_size)
        block_datas = []
        for s, e in blocks:
            mask = np.zeros(data.count, dtype=bool); mask[s:e] = True
            bd = data.subset(mask)
            if bd.count == 0:
                continue
            _write_spx_v1_splat20_block(f, bd)
            block_datas.append(bd)
        for bd in block_datas:
            if sh_degree >= 1:
                _write_sh_block(f, bd, BF_SH1, 9)
            if sh_degree >= 2:
                _write_sh_block(f, bd, BF_SH2, 24)
            if sh_degree >= 3:
                _write_sh_block(f, bd, BF_SH3, 21, src_offset=24)


def _write_spx_v1_splat20_block(f, block_data):
    count = block_data.count
    import math
    bts = bytearray()
    bts += struct.pack('<II', count, BF_SPLAT20)
    for i in range(count):
        bts += codec.encode_spx_position_uint24(float(block_data.position[i, 0]))
    for i in range(count):
        bts += codec.encode_spx_position_uint24(float(block_data.position[i, 1]))
    for i in range(count):
        bts += codec.encode_spx_position_uint24(float(block_data.position[i, 2]))
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 0])))
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 1])))
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 2])))
    for i in range(count):
        bts.append(int(block_data.color[i, 0]))
    for i in range(count):
        bts.append(int(block_data.color[i, 1]))
    for i in range(count):
        bts.append(int(block_data.color[i, 2]))
    for i in range(count):
        bts.append(int(block_data.color[i, 3]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 0]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 1]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 2]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 3]))
    f.write(_make_block_header(bytes(bts), CT_GZIP))


def _write_sh_block(f, block_data, format_id, sh_size, src_offset=0):
    count = block_data.count
    bts = bytearray()
    bts += struct.pack('<II', count, format_id)
    for i in range(count):
        for j in range(sh_size):
            bts.append(int(block_data.sh[i, src_offset + j]))
    if all(b == 128 for b in bts[8:]):
        return
    f.write(_make_block_header(bytes(bts), CT_GZIP))


def _write_spx_v2(file_path, data, comment, sh_degree, block_size, block_format, quality):
    header = gen_spx_header_v3(data, comment, sh_degree)
    header.version = 2
    header_bytes = spx_header_to_bytes(header)
    with open(file_path, 'wb') as f:
        f.write(header_bytes)
        blocks = _build_blocks(data.count, block_size)
        block_datas = []
        for s, e in blocks:
            mask = np.zeros(data.count, dtype=bool); mask[s:e] = True
            bd = data.subset(mask)
            if bd.count == 0:
                continue
            if block_format == BF_SPLAT190_WEBP and bd.count >= MIN_WEBP_BLOCK_SIZE:
                _write_v2_spx_190_webp_block(f, bd, quality)
            else:
                _write_v2_spx_19_block(f, bd, block_format, quality)
            block_datas.append(bd)
        if sh_degree > 0 and block_format == BF_SPLAT190_WEBP:
            for bd in block_datas:
                _write_v2_sh3_webp_block(f, bd, quality)
        else:
            for bd in block_datas:
                if sh_degree >= 1:
                    _write_sh_block(f, bd, BF_SH1, 9)
                if sh_degree >= 2:
                    _write_sh_block(f, bd, BF_SH2, 24)
                if sh_degree >= 3:
                    _write_v2_sh3_block(f, bd)
                    _write_sh_block(f, bd, BF_SH3, 21, src_offset=24)


def _write_v2_spx_19_block(f, block_data, block_format, quality):
    count = block_data.count
    bts = bytearray()
    bts += struct.pack('<II', count, BF_SPLAT19)
    bs0, bs1, bs2 = bytearray(), bytearray(), bytearray()
    for i in range(count):
        b0, b1, b2 = codec.encode_spx_position_uint24(float(block_data.position[i, 0]))
        bs0.append(b0); bs1.append(b1); bs2.append(b2)
    for i in range(count):
        b0, b1, b2 = codec.encode_spx_position_uint24(float(block_data.position[i, 1]))
        bs0.append(b0); bs1.append(b1); bs2.append(b2)
    for i in range(count):
        b0, b1, b2 = codec.encode_spx_position_uint24(float(block_data.position[i, 2]))
        bs0.append(b0); bs1.append(b1); bs2.append(b2)
    bts += bs0 + bs1 + bs2
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 0])))
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 1])))
    for i in range(count):
        bts.append(codec.encode_spx_scale(float(block_data.scale[i, 2])))
    for i in range(count):
        bts.append(int(block_data.color[i, 0]))
    for i in range(count):
        bts.append(int(block_data.color[i, 1]))
    for i in range(count):
        bts.append(int(block_data.color[i, 2]))
    for i in range(count):
        bts.append(int(block_data.color[i, 3]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 1]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 2]))
    for i in range(count):
        bts.append(int(block_data.rotation[i, 3]))
    f.write(_make_block_header(bytes(bts), CT_GZIP))


def _write_v2_spx_190_webp_block(f, block_data, quality):
    count = block_data.count
    bs0, bs1, bs2 = bytearray(), bytearray(), bytearray()
    for i in range(count):
        pb = codec.encode_spx_position_uint24(float(block_data.position[i, 0]))
        bs0.append(pb[0]); bs1.append(pb[1]); bs2.append(pb[2])
        bs0.append(255); bs1.append(255); bs2.append(255)
    for i in range(count):
        pb = codec.encode_spx_position_uint24(float(block_data.position[i, 1]))
        bs0.append(pb[0]); bs1.append(pb[1]); bs2.append(pb[2])
        bs0.append(255); bs1.append(255); bs2.append(255)
    for i in range(count):
        pb = codec.encode_spx_position_uint24(float(block_data.position[i, 2]))
        bs0.append(pb[0]); bs1.append(pb[1]); bs2.append(pb[2])
        bs0.append(255); bs1.append(255); bs2.append(255)
    pos_img = bytes(bs0 + bs1 + bs2)
    pos_webp = compress.compress_webp(pos_img, quality=quality)

    sc_buf = bytearray()
    for i in range(count):
        sc_buf.append(codec.encode_spx_scale(float(block_data.scale[i, 0])))
        sc_buf.append(codec.encode_spx_scale(float(block_data.scale[i, 1])))
        sc_buf.append(codec.encode_spx_scale(float(block_data.scale[i, 2])))
        sc_buf.append(255)
    sc_webp = compress.compress_webp(bytes(sc_buf), quality=quality)

    c_buf = bytearray()
    for i in range(count):
        c_buf.append(int(block_data.color[i, 0]))
        c_buf.append(int(block_data.color[i, 1]))
        c_buf.append(int(block_data.color[i, 2]))
        c_buf.append(int(block_data.color[i, 3]))
    c_webp = compress.compress_webp(bytes(c_buf), quality=quality)

    r_buf = bytearray()
    for i in range(count):
        r_buf.append(int(block_data.rotation[i, 1]))
        r_buf.append(int(block_data.rotation[i, 2]))
        r_buf.append(int(block_data.rotation[i, 3]))
        r_buf.append(255)
    r_webp = compress.compress_webp(bytes(r_buf), quality=quality)

    bts = struct.pack('<II', count, BF_SPLAT190_WEBP)
    for webp in (pos_webp, sc_webp, c_webp, r_webp):
        bts += struct.pack('<I', len(webp)) + webp
    f.write(_make_block_header(bts, 0))


def _write_v2_sh3_block(f, block_data):
    count = block_data.count
    bts = bytearray()
    bts += struct.pack('<II', count, BF_SH2)
    for i in range(count):
        for j in range(24):
            bts.append(int(block_data.sh[i, j]))
    f.write(_make_block_header(bytes(bts), CT_GZIP))


def _write_v2_sh3_webp_block(f, block_data, quality):
    count = block_data.count
    bts = bytearray()
    bts += struct.pack('<II', count, BF_SH3_WEBP)
    sh_rgba = bytearray()
    for i in range(count):
        for b in range(15):
            sh_rgba.append(codec.encode_spx_sh(int(block_data.sh[i, b * 3 + 0])))
            sh_rgba.append(codec.encode_spx_sh(int(block_data.sh[i, b * 3 + 1])))
            sh_rgba.append(codec.encode_spx_sh(int(block_data.sh[i, b * 3 + 2])))
            sh_rgba.append(255)
    bts += compress.compress_webp(bytes(sh_rgba), quality=quality)
    f.write(struct.pack('<i', len(bts)) + bts)


def _write_spx_v3_write(file_path, data, comment, sh_degree, block_size, block_format, quality):
    header = gen_spx_header_v3(data, comment, sh_degree)
    header_bytes = spx_header_to_bytes(header)

    with open(file_path, 'wb') as f:
        f.write(header_bytes)

        total = data.count
        if total == 0:
            return

        blocks = _build_blocks(total, block_size)
        palettes_block = _compute_palettes_block_index(blocks, sh_degree, block_format)

        for bi, (s, e) in enumerate(blocks):
            mask = np.zeros(data.count, dtype=bool)
            mask[s:e] = True
            block_data = data.subset(mask)

            if block_data.count == 0:
                continue

            if block_format in (BF_SPLAT220_WEBP, BF_SPLAT230_WEBP):
                _write_spx_webp_block_v3(f, block_data, sh_degree, block_format, quality)
            else:
                _write_spx_block_v3(f, block_data, sh_degree, CT_GZIP, block_format)

            if bi == palettes_block and sh_degree > 0:
                _write_palettes_webp_block(f, data, sh_degree, quality)


def _build_blocks(total: int, block_size: int) -> List[Tuple[int, int]]:
    block_count = max(1, (total + block_size - 1) // block_size)
    blocks: List[Tuple[int, int]] = []

    for bi in range(block_count):
        start = bi * block_size
        end = min(start + block_size, total)
        blocks.append((start, end))

    if len(blocks) > 1:
        last_start = blocks[-1][0]
        if blocks[-1][1] - last_start < MIN_BLOCK_SIZE:
            blocks.pop()
            blocks[-1] = (blocks[-1][0], total)

    return blocks


def _compute_palettes_block_index(blocks: list, sh_degree: int, block_format: int) -> int:
    if sh_degree <= 0:
        return -1
    if block_format not in (BF_SPLAT220_WEBP, BF_SPLAT230_WEBP):
        return -1
    if len(blocks) <= 1:
        return 0
    return max(1, len(blocks) // 3)


def _make_block_header(raw_data: bytes, compress_type: int) -> bytes:
    use_compression = len(raw_data) > 256 and compress_type == CT_GZIP
    if use_compression:
        compressed = compress.compress_gzip(raw_data)
        if len(compressed) < len(raw_data):
            encoded_size = -((compress_type << 28) | len(compressed))
            return struct.pack('<i', encoded_size) + compressed
    return struct.pack('<i', len(raw_data)) + raw_data


def _write_spx_block_v3(f, block_data: SplatData, sh_degree: int, compress_type: int, bf: int):
    count = block_data.count
    log_times = 1

    payload = _encode_channels_interleaved(block_data, log_times)
    raw_block = struct.pack('<II', count, bf) + payload
    block_bytes = _make_block_header(raw_block, compress_type)
    f.write(block_bytes)


def _encode_channels_interleaved(block_data: SplatData, log_times: int) -> bytes:
    count = block_data.count
    result = bytearray()

    pos_enc = np.zeros((count, 3, 3), dtype=np.uint8)
    for ax in range(3):
        for i in range(count):
            val = codec.encode_log(float(block_data.position[i, ax]), log_times)
            bts = codec.encode_spx_position_uint24(val)
            pos_enc[i, ax, 0] = bts[0]
            pos_enc[i, ax, 1] = bts[1]
            pos_enc[i, ax, 2] = bts[2]

    for byte_idx in range(3):
        for axis in range(3):
            for i in range(count):
                result.append(int(pos_enc[i, axis, byte_idx]))

    for axis in range(3):
        for i in range(count):
            result.append(codec.encode_spx_scale(float(block_data.scale[i, axis])))

    for comp in range(4):
        for i in range(count):
            result.append(int(block_data.color[i, comp]))

    for comp in range(4):
        for i in range(count):
            result.append(int(block_data.rotation[i, comp]))

    for comp in range(2):
        for i in range(count):
            val = int(block_data.palette_idx[i])
            result.append(val & 0xFF if comp == 0 else (val >> 8) & 0xFF)

    for comp in range(2):
        for i in range(count):
            val = int(block_data.flag_value[i])
            result.append(val & 0xFF if comp == 0 else (val >> 8) & 0xFF)

    return bytes(result)


def _write_spx_webp_block_v3(f, block_data: SplatData, sh_degree: int, bf: int, quality: int):
    count = block_data.count
    log_times = 1

    payload = _encode_channels_webp(block_data, log_times, quality)
    raw_block = struct.pack('<II', count, bf) + payload
    block_bytes = _make_block_header(raw_block, CT_GZIP)
    f.write(block_bytes)


def _encode_channels_webp(block_data: SplatData, log_times: int, quality: int) -> bytes:
    count = block_data.count

    pos0_buf, pos1_buf, pos2_buf = _build_position_image_buffers(block_data, count, log_times)
    scale_buf = _build_scale_image_buffer(block_data, count)
    color_buf = _build_color_image_buffer(block_data, count)
    rot_buf = _build_rotation_image_buffer(block_data, count)
    pal_buf = _build_palette_image_buffer(block_data, count)
    flag_buf = _build_flag_image_buffer(block_data, count)

    result = bytearray()
    result.extend(_webp_channel_header(pos0_buf, quality))
    result.extend(_webp_channel_header(pos1_buf, quality))
    result.extend(_webp_channel_header(pos2_buf, quality))
    result.extend(_webp_channel_header(scale_buf, quality))
    result.extend(_webp_channel_header(color_buf, quality))
    result.extend(_webp_channel_header(rot_buf, quality))
    result.extend(_webp_channel_header(pal_buf, quality))
    result.extend(_webp_channel_header(flag_buf, quality))

    return bytes(result)


def _webp_channel_header(rgba_data: bytes, quality: int) -> bytes:
    if len(rgba_data) == 0:
        return struct.pack('<I', 0)
    num_pixels = len(rgba_data) // 4
    w, h = compress.compute_width_height(num_pixels * 4)
    needed = w * h * 4
    if len(rgba_data) < needed:
        padded = bytearray(rgba_data)
        padded.extend(b'\xff\xff\xff\xff' * (needed // 4 - num_pixels))
        rgba_data = bytes(padded)
    webp_data = compress.compress_webp(rgba_data, width=w, height=h, quality=quality)
    return struct.pack('<I', len(webp_data)) + webp_data


def _build_position_image_buffers(block_data: SplatData, count: int, log_times: int) -> Tuple[bytes, bytes, bytes]:
    pos_enc = np.zeros((count, 3, 3), dtype=np.uint8)
    for ax in range(3):
        for i in range(count):
            val = codec.encode_log(float(block_data.position[i, ax]), log_times)
            bts = codec.encode_spx_position_uint24(val)
            pos_enc[i, ax, 0] = bts[0]
            pos_enc[i, ax, 1] = bts[1]
            pos_enc[i, ax, 2] = bts[2]

    pos0_arr = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    pos1_arr = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    pos2_arr = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)

    pos0_arr[:count, 0] = pos_enc[:count, 0, 0]
    pos0_arr[:count, 1] = pos_enc[:count, 1, 0]
    pos0_arr[:count, 2] = pos_enc[:count, 2, 0]

    pos1_arr[:count, 0] = pos_enc[:count, 0, 1]
    pos1_arr[:count, 1] = pos_enc[:count, 1, 1]
    pos1_arr[:count, 2] = pos_enc[:count, 2, 1]

    pos2_arr[:count, 0] = pos_enc[:count, 0, 2]
    pos2_arr[:count, 1] = pos_enc[:count, 1, 2]
    pos2_arr[:count, 2] = pos_enc[:count, 2, 2]

    return pos0_arr.tobytes(), pos1_arr.tobytes(), pos2_arr.tobytes()


def _build_scale_image_buffer(block_data: SplatData, count: int) -> bytes:
    buf = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    for ax in range(3):
        for i in range(count):
            buf[i, ax] = codec.encode_spx_scale(float(block_data.scale[i, ax]))
    return buf.tobytes()


def _build_color_image_buffer(block_data: SplatData, count: int) -> bytes:
    buf = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    buf[:count, :4] = block_data.color[:count, :4]
    return buf.tobytes()


def _build_rotation_image_buffer(block_data: SplatData, count: int) -> bytes:
    buf = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    for i in range(count):
        rw, rx, ry, rz = (
            int(block_data.rotation[i, 0]),
            int(block_data.rotation[i, 1]),
            int(block_data.rotation[i, 2]),
            int(block_data.rotation[i, 3]),
        )
        r0, r1, r2, ri = codec.sog_encode_rotations(rw, rx, ry, rz)
        buf[i, 0] = r0
        buf[i, 1] = r1
        buf[i, 2] = r2
        buf[i, 3] = ri
    return buf.tobytes()


def _build_palette_image_buffer(block_data: SplatData, count: int) -> bytes:
    buf = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    for i in range(count):
        val = int(block_data.palette_idx[i])
        buf[i, 0] = val & 0xFF
        buf[i, 1] = (val >> 8) & 0xFF
    return buf.tobytes()


def _build_flag_image_buffer(block_data: SplatData, count: int) -> bytes:
    buf = np.full(count * 4, 255, dtype=np.uint8).reshape(-1, 4)
    for i in range(count):
        val = int(block_data.flag_value[i])
        buf[i, 0] = val & 0xFF
        buf[i, 1] = (val >> 8) & 0xFF
    return buf.tobytes()


def _write_palettes_block(f, data: SplatData, sh_degree: int):
    palettes = _sh_palettes_to_bytes(data, sh_degree)
    count = len(palettes) // PALETTE_ENTRY_SIZE
    raw_block = struct.pack('<II', count, BF_SH_PALETTES) + palettes
    block_bytes = _make_block_header(raw_block, CT_GZIP)
    f.write(block_bytes)


def _write_palettes_webp_block(f, data: SplatData, sh_degree: int, quality: int = 90):
    palettes = _sh_palettes_to_bytes(data, sh_degree)
    palette_count = len(palettes) // PALETTE_ENTRY_SIZE
    if palette_count == 0:
        return

    webp_data = compress.compress_webp(palettes, quality=quality)
    payload = struct.pack('<I', len(webp_data)) + webp_data
    raw_block = struct.pack('<II', palette_count, BF_SH_PALETTES_WEBP) + payload
    block_bytes = _make_block_header(raw_block, CT_GZIP)
    f.write(block_bytes)


def _sh_palettes_to_bytes(data: SplatData, sh_degree: int) -> bytes:
    if sh_degree <= 0 or data.count == 0:
        return b''

    sh_band_count = {1: 3, 2: 8, 3: 15}.get(sh_degree, 15)
    component_count = sh_band_count * 3

    palettes_dict: dict = {}
    palettes_order: List[int] = []
    next_id = 0

    for i in range(data.count):
        pid = int(data.palette_idx[i])
        if pid not in palettes_dict:
            palettes_dict[pid] = next_id
            palettes_order.append(pid)
            next_id += 1

    total_palettes = len(palettes_order) if palettes_order else 1
    result = bytearray()
    result.extend(total_palettes.to_bytes(4, 'little'))

    palette_data_size = max(1, total_palettes) * PALETTE_ENTRY_SIZE
    palette_bytes = bytearray(palette_data_size)

    for new_idx, old_pid in enumerate(palettes_order):
        for i in range(data.count):
            if int(data.palette_idx[i]) == old_pid:
                offset = new_idx * PALETTE_ENTRY_SIZE
                for b in range(component_count):
                    if b < SH_BANDS_TOTAL:
                        palette_bytes[offset + b * 1] = int(data.sh[i, b])
                break

    if not palettes_order and data.count > 0:
        offset = 0
        for b in range(component_count):
            if b < SH_BANDS_TOTAL:
                palette_bytes[offset + b * 1] = int(data.sh[0, b])

    result.extend(palette_bytes)
    return bytes(result)
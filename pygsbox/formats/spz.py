import os
import struct
import numpy as np
from typing import Tuple, List, Optional
from ..core.splat_data import SplatData
from ..common import codec, compress
from ..common.progress import Progress, PHASE_READ, PHASE_WRITE

SPZ_MAGIC = 0x5053474E
HEADER_SIZE_V3 = 16
HEADER_SIZE_V4 = 32


class SpzHeader:
    def __init__(self):
        self.magic: int = 0
        self.version: int = 0
        self.num_points: int = 0
        self.sh_degree: int = 0
        self.fractional_bits: int = 0
        self.flags: int = 0
        self.num_streams: int = 0
        self.toc_byte_offset: int = 0
        self.reserved: int = 0

    def to_string(self) -> str:
        return (
            f"SpzHeader(version={self.version}, num_points={self.num_points}, "
            f"sh_degree={self.sh_degree}, fractional_bits={self.fractional_bits}, "
            f"flags={self.flags})"
        )


def _parse_spz_header(data: bytes) -> SpzHeader:
    magic = struct.unpack('<I', data[0:4])[0]
    if magic != SPZ_MAGIC:
        raise ValueError(f"Invalid SPZ magic: {magic:#x}")

    version = struct.unpack('<I', data[4:8])[0]
    header = SpzHeader()
    header.magic = magic
    header.version = version
    header.num_points = struct.unpack('<I', data[8:12])[0]
    header.sh_degree = data[12]
    header.fractional_bits = data[13]
    header.flags = data[14]

    if version == 2 or version == 3:
        header.reserved = data[15]
    elif version == 4:
        header.num_streams = data[15]
        header.toc_byte_offset = struct.unpack('<I', data[16:20])[0]
    else:
        raise ValueError(f"Unsupported SPZ version: {version}")

    if header.sh_degree > 3:
        raise ValueError(f"Unsupported SH degree: {header.sh_degree}")
    if header.fractional_bits != 12:
        raise ValueError(f"Unsupported FractionalBits: {header.fractional_bits}")

    return header


def _spz_header_to_bytes(header: SpzHeader) -> bytes:
    if header.version < 4:
        bts = struct.pack('<III', header.magic, header.version, header.num_points)
        bts += bytes([header.sh_degree, header.fractional_bits, header.flags, header.reserved])
        return bts
    bts = struct.pack('<III', header.magic, header.version, header.num_points)
    bts += bytes([header.sh_degree, header.fractional_bits, header.flags, header.num_streams])
    bts += struct.pack('<I', header.toc_byte_offset)
    bts += b'\x00' * 12
    return bts


def read_spz(file_path: str) -> Tuple[SpzHeader, SplatData]:
    with open(file_path, 'rb') as f:
        raw = f.read()

    if len(raw) >= 8 and struct.unpack('<I', raw[0:4])[0] == SPZ_MAGIC:
        version = struct.unpack('<I', raw[4:8])[0]
        if version == 4:
            header = _parse_spz_header(raw[:HEADER_SIZE_V4])
            data = _read_spz_v4(raw, header)
            return header, data

    decompressed = compress.decompress_gzip(raw)
    if len(decompressed) < HEADER_SIZE_V3:
        raise ValueError("Invalid SPZ data after decompression")

    header = _parse_spz_header(decompressed[:HEADER_SIZE_V3])
    data = _read_spz_v2v3(decompressed[HEADER_SIZE_V3:], header)
    return header, data


def _read_spz_v2v3(datas: bytes, header: SpzHeader) -> SplatData:
    n = header.num_points
    position_size = n * 9
    alpha_size = n
    color_size = n * 3
    scale_size = n * 3
    rotation_size = n * 3
    per_splat_size = 19
    if header.version >= 3:
        rotation_size = n * 4
        per_splat_size = 20

    sh_dim = {1: n * 9, 2: n * 24, 3: n * 45}.get(header.sh_degree, 0)
    if len(datas) != n * per_splat_size + sh_dim:
        raise ValueError(
            f"Invalid SPZ data size: expected {n * per_splat_size + sh_dim}, got {len(datas)}"
        )

    off_pos = 0
    off_alpha = off_pos + position_size
    off_color = off_alpha + alpha_size
    off_scale = off_color + color_size
    off_rot = off_scale + scale_size
    off_sh = off_rot + rotation_size

    positions = datas[off_pos:off_pos + position_size]
    alphas = datas[off_alpha:off_alpha + alpha_size]
    colors = datas[off_color:off_color + color_size]
    scales = datas[off_scale:off_scale + scale_size]
    rotations = datas[off_rot:off_rot + rotation_size]
    shs = datas[off_sh:] if sh_dim > 0 else b''

    data = SplatData(n)

    for i in range(n):
        Progress.report(PHASE_READ, i, n)
        data.position[i, 0] = codec.spz_decode_position(positions[i * 9:i * 9 + 3], header.fractional_bits)
        data.position[i, 1] = codec.spz_decode_position(positions[i * 9 + 3:i * 9 + 6], header.fractional_bits)
        data.position[i, 2] = codec.spz_decode_position(positions[i * 9 + 6:i * 9 + 9], header.fractional_bits)

        data.scale[i, 0] = codec.spz_decode_scale(scales[i * 3])
        data.scale[i, 1] = codec.spz_decode_scale(scales[i * 3 + 1])
        data.scale[i, 2] = codec.spz_decode_scale(scales[i * 3 + 2])

        data.color[i, 0] = codec.spz_decode_color(colors[i * 3])
        data.color[i, 1] = codec.spz_decode_color(colors[i * 3 + 1])
        data.color[i, 2] = codec.spz_decode_color(colors[i * 3 + 2])

        data.color[i, 3] = alphas[i]

        if header.version == 2:
            data.rotation[i] = codec.spz_decode_rotations(
                rotations[i * 3], rotations[i * 3 + 1], rotations[i * 3 + 2]
            )
        else:
            data.rotation[i] = codec.spz_decode_rotations_v3v4(rotations[i * 4:i * 4 + 4])

        if header.sh_degree == 1:
            data.sh[i, :9] = list(shs[i * 9:i * 9 + 9])
        elif header.sh_degree == 2:
            data.sh[i, :24] = list(shs[i * 24:i * 24 + 24])
        elif header.sh_degree == 3:
            data.sh[i, :45] = list(shs[i * 45:i * 45 + 45])

    return data


def _read_spz_v4(raw: bytes, header: SpzHeader) -> SplatData:
    n = header.num_points
    toc_data = raw[header.toc_byte_offset:]

    zstd_sizes = []
    offset = 0
    for _ in range(header.num_streams):
        size = struct.unpack('<Q', toc_data[offset:offset + 8])[0]
        offset += 16
        zstd_sizes.append(size)

    stream_data = toc_data[offset + 0 if header.num_streams == 0
                            else header.num_streams * 16 - offset
                            if offset < header.num_streams * 16
                            else header.num_streams * 16:]
    stream_data = toc_data[header.num_streams * 16:]

    positions = compress.decompress_zstd(stream_data[:zstd_sizes[0]])
    remaining = stream_data[zstd_sizes[0]:]

    alphas = compress.decompress_zstd(remaining[:zstd_sizes[1]])
    remaining = remaining[zstd_sizes[1]:]

    colors = compress.decompress_zstd(remaining[:zstd_sizes[2]])
    remaining = remaining[zstd_sizes[2]:]

    scales = compress.decompress_zstd(remaining[:zstd_sizes[3]])
    remaining = remaining[zstd_sizes[3]:]

    rotations = compress.decompress_zstd(remaining[:zstd_sizes[4]])
    remaining = remaining[zstd_sizes[4]:]

    shs = b''
    if header.num_streams > 5:
        shs = compress.decompress_zstd(remaining[:zstd_sizes[5]])

    data = SplatData(n)

    for i in range(n):
        Progress.report(PHASE_READ, i, n)
        data.position[i, 0] = codec.spz_decode_position(positions[i * 9:i * 9 + 3], header.fractional_bits)
        data.position[i, 1] = codec.spz_decode_position(positions[i * 9 + 3:i * 9 + 6], header.fractional_bits)
        data.position[i, 2] = codec.spz_decode_position(positions[i * 9 + 6:i * 9 + 9], header.fractional_bits)

        data.scale[i, 0] = codec.spz_decode_scale(scales[i * 3])
        data.scale[i, 1] = codec.spz_decode_scale(scales[i * 3 + 1])
        data.scale[i, 2] = codec.spz_decode_scale(scales[i * 3 + 2])

        data.color[i, 0] = codec.spz_decode_color(colors[i * 3])
        data.color[i, 1] = codec.spz_decode_color(colors[i * 3 + 1])
        data.color[i, 2] = codec.spz_decode_color(colors[i * 3 + 2])

        data.color[i, 3] = alphas[i]

        data.rotation[i] = codec.spz_decode_rotations_v3v4(rotations[i * 4:i * 4 + 4])

        if header.sh_degree == 1:
            data.sh[i, :9] = list(shs[i * 9:i * 9 + 9])
        elif header.sh_degree == 2:
            data.sh[i, :24] = list(shs[i * 24:i * 24 + 24])
        elif header.sh_degree == 3:
            data.sh[i, :45] = list(shs[i * 45:i * 45 + 45])

    return data


def write_spz(file_path: str, data: SplatData, sh_degree: int = 0, version: int = 4):
    os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)

    if version < 4:
        _write_spz_v2v3(file_path, data, sh_degree, version)
    else:
        _write_spz_v4(file_path, data, sh_degree)


def _write_spz_v2v3(file_path: str, data: SplatData, sh_degree: int, version: int):
    n = data.count

    header = SpzHeader()
    header.magic = SPZ_MAGIC
    header.version = version
    header.num_points = n
    header.sh_degree = sh_degree
    header.fractional_bits = 12
    header.flags = 0
    header.reserved = 0

    bts = bytearray()
    bts.extend(_spz_header_to_bytes(header))

    for i in range(n):
        bts.extend(codec.spz_encode_position(float(data.position[i, 0])))
        bts.extend(codec.spz_encode_position(float(data.position[i, 1])))
        bts.extend(codec.spz_encode_position(float(data.position[i, 2])))

    for i in range(n):
        bts.append(int(data.color[i, 3]))

    for i in range(n):
        bts.append(codec.spz_encode_color(int(data.color[i, 0])))
        bts.append(codec.spz_encode_color(int(data.color[i, 1])))
        bts.append(codec.spz_encode_color(int(data.color[i, 2])))

    for i in range(n):
        bts.append(codec.spz_encode_scale(float(data.scale[i, 0])))
        bts.append(codec.spz_encode_scale(float(data.scale[i, 1])))
        bts.append(codec.spz_encode_scale(float(data.scale[i, 2])))

    if version >= 3:
        for i in range(n):
            bts.extend(codec.spz_encode_rotations_v3v4(
                int(data.rotation[i, 0]), int(data.rotation[i, 1]),
                int(data.rotation[i, 2]), int(data.rotation[i, 3])
            ))
    else:
        for i in range(n):
            bts.extend(codec.spz_encode_rotations(
                int(data.rotation[i, 0]), int(data.rotation[i, 1]),
                int(data.rotation[i, 2]), int(data.rotation[i, 3])
            ))

    if sh_degree > 0:
        sh_counts = {1: 9, 2: 24, 3: 45}.get(sh_degree, 0)
        for i in range(n):
            for j in range(9):
                bts.append(codec.spz_encode_sh1(int(data.sh[i, j])))
            for j in range(9, sh_counts):
                bts.append(codec.spz_encode_sh23(int(data.sh[i, j])))

    compressed = compress.compress_gzip(bytes(bts))
    with open(file_path, 'wb') as f:
        f.write(compressed)


def _write_spz_v4(file_path: str, data: SplatData, sh_degree: int):
    n = data.count
    num_streams = 5 if sh_degree == 0 else 6

    header = SpzHeader()
    header.magic = SPZ_MAGIC
    header.version = 4
    header.num_points = n
    header.sh_degree = sh_degree
    header.fractional_bits = 12
    header.flags = 0
    header.num_streams = num_streams
    header.toc_byte_offset = 32

    positions = bytearray()
    for i in range(n):
        positions.extend(codec.spz_encode_position(float(data.position[i, 0])))
        positions.extend(codec.spz_encode_position(float(data.position[i, 1])))
        positions.extend(codec.spz_encode_position(float(data.position[i, 2])))

    alphas = bytearray()
    for i in range(n):
        alphas.append(int(data.color[i, 3]))

    colors = bytearray()
    for i in range(n):
        colors.append(codec.spz_encode_color(int(data.color[i, 0])))
        colors.append(codec.spz_encode_color(int(data.color[i, 1])))
        colors.append(codec.spz_encode_color(int(data.color[i, 2])))

    scales = bytearray()
    for i in range(n):
        scales.append(codec.spz_encode_scale(float(data.scale[i, 0])))
        scales.append(codec.spz_encode_scale(float(data.scale[i, 1])))
        scales.append(codec.spz_encode_scale(float(data.scale[i, 2])))

    rotations = bytearray()
    for i in range(n):
        rotations.extend(codec.spz_encode_rotations_v3v4(
            int(data.rotation[i, 0]), int(data.rotation[i, 1]),
            int(data.rotation[i, 2]), int(data.rotation[i, 3])
        ))

    shs = bytearray()
    if sh_degree > 0:
        sh_counts = {1: 9, 2: 24, 3: 45}.get(sh_degree, 0)
        for i in range(n):
            for j in range(9):
                shs.append(codec.spz_encode_sh1(int(data.sh[i, j])))
            for j in range(9, sh_counts):
                shs.append(codec.spz_encode_sh23(int(data.sh[i, j])))

    zstd_positions = compress.compress_zstd(bytes(positions))
    zstd_alphas = compress.compress_zstd(bytes(alphas))
    zstd_colors = compress.compress_zstd(bytes(colors))
    zstd_scales = compress.compress_zstd(bytes(scales))
    zstd_rotations = compress.compress_zstd(bytes(rotations))

    toc = bytearray()
    streams = [
        (zstd_positions, positions),
        (zstd_alphas, alphas),
        (zstd_colors, colors),
        (zstd_scales, scales),
        (zstd_rotations, rotations),
    ]
    if sh_degree > 0:
        zstd_shs = compress.compress_zstd(bytes(shs))
        streams.append((zstd_shs, shs))

    for zstd_data, _ in streams:
        toc.extend(struct.pack('<QQ', len(zstd_data), 0))

    bts = bytearray()
    bts.extend(_spz_header_to_bytes(header))
    bts.extend(toc)
    for zstd_data, _ in streams:
        bts.extend(zstd_data)

    with open(file_path, 'wb') as f:
        f.write(bytes(bts))

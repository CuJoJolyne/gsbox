import struct
import math
import numpy as np
from typing import Tuple, Optional
from ..core.splat_data import SplatData
from ..common import codec

KSPLAT_HEAD_SIZE = 4096
KSPLAT_SECTION_SIZE = 1024


class KsplatHeader:
    def __init__(self):
        self.major_version: int = 0
        self.minor_version: int = 0
        self.section_count: int = 0
        self.splat_count: int = 0
        self.compression_mode: int = 0
        self.min_harmonics_value: float = -1.5
        self.max_harmonics_value: float = 1.5
        self.sh_degree: int = 0

    def to_string(self) -> str:
        return (
            f"KsplatHeader(v={self.major_version}.{self.minor_version}, "
            f"sections={self.section_count}, splats={self.splat_count}, "
            f"mode={self.compression_mode}, sh_degree={self.sh_degree})"
        )


class SectionHeader:
    def __init__(self):
        self.splat_count: int = 0
        self.splat_capacity: int = 0
        self.bucket_capacity: int = 0
        self.bucket_count: int = 0
        self.block_size: float = 0.0
        self.bucket_size: int = 0
        self.quantization_range: int = 0
        self.full_bucket_count: int = 0
        self.partial_bucket_count: int = 0
        self.sh_degree: int = 0


def read_ksplat(file_path: str) -> Tuple[KsplatHeader, SplatData]:
    with open(file_path, 'rb') as f:
        header_bytes = f.read(KSPLAT_HEAD_SIZE)

    if len(header_bytes) < KSPLAT_HEAD_SIZE:
        raise ValueError("File too small for KSplat header")

    main_header = KsplatHeader()
    main_header.major_version = header_bytes[0]
    main_header.minor_version = header_bytes[1]
    main_header.section_count = struct.unpack('<i', header_bytes[4:8])[0]
    main_header.splat_count = struct.unpack('<i', header_bytes[16:20])[0]
    main_header.compression_mode = struct.unpack('<H', header_bytes[20:22])[0]
    main_header.min_harmonics_value = struct.unpack('<f', header_bytes[36:40])[0]
    main_header.max_harmonics_value = struct.unpack('<f', header_bytes[40:44])[0]

    if main_header.major_version != 0 or main_header.minor_version != 1:
        raise ValueError(f"Unsupported KSplat version: {main_header.major_version}.{main_header.minor_version}")
    if main_header.compression_mode > 2:
        raise ValueError(f"Invalid compression mode: {main_header.compression_mode}")
    if main_header.splat_count == 0:
        raise ValueError("KSplat data empty")
    if main_header.min_harmonics_value == 0:
        main_header.min_harmonics_value = -1.5
    if main_header.max_harmonics_value == 0:
        main_header.max_harmonics_value = 1.5

    cm = main_header.compression_mode
    if cm == 0:
        center_bytes, scale_bytes = 12, 12
        rotation_bytes, color_bytes, harmonics_bytes = 16, 4, 4
        scale_start, color_start, harmonics_start = 12, 40, 44
        rotation_start = 24
        scale_quant_range = 1
    elif cm == 1:
        center_bytes, scale_bytes = 6, 6
        rotation_bytes, color_bytes, harmonics_bytes = 8, 4, 2
        scale_start, color_start, harmonics_start = 6, 20, 24
        rotation_start = 12
        scale_quant_range = 32767
    else:
        center_bytes, scale_bytes = 6, 6
        rotation_bytes, color_bytes, harmonics_bytes = 8, 4, 1
        scale_start, color_start, harmonics_start = 6, 20, 24
        rotation_start = 12
        scale_quant_range = 32767

    section_headers = []
    for i in range(main_header.section_count):
        with open(file_path, 'rb') as f:
            f.seek(KSPLAT_HEAD_SIZE + i * KSPLAT_SECTION_SIZE)
            sec_bytes = f.read(KSPLAT_SECTION_SIZE)
        sec = SectionHeader()
        sec.splat_count = struct.unpack('<I', sec_bytes[0:4])[0]
        sec.splat_capacity = struct.unpack('<I', sec_bytes[4:8])[0]
        sec.bucket_capacity = struct.unpack('<I', sec_bytes[8:12])[0]
        sec.bucket_count = struct.unpack('<I', sec_bytes[12:16])[0]
        sec.block_size = struct.unpack('<f', sec_bytes[16:20])[0]
        sec.bucket_size = struct.unpack('<H', sec_bytes[20:22])[0]
        sec.quantization_range = struct.unpack('<I', sec_bytes[24:28])[0]
        sec.full_bucket_count = struct.unpack('<I', sec_bytes[32:36])[0]
        sec.partial_bucket_count = struct.unpack('<I', sec_bytes[36:40])[0]
        sec.sh_degree = struct.unpack('<H', sec_bytes[40:42])[0]
        if sec.quantization_range == 0:
            sec.quantization_range = scale_quant_range
        section_headers.append(sec)
        if main_header.sh_degree < sec.sh_degree:
            main_header.sh_degree = sec.sh_degree

    sh_dims_map = [0, 9, 24, 15]
    sh_components = sh_dims_map[main_header.sh_degree]
    offset = KSPLAT_HEAD_SIZE + main_header.section_count * KSPLAT_SECTION_SIZE
    data = SplatData(main_header.splat_count)
    n = 0

    for i in range(main_header.section_count):
        sec = section_headers[i]
        bytes_per_splat = (
            center_bytes + scale_bytes + rotation_bytes +
            color_bytes + harmonics_bytes * sh_components
        )
        position_scale_factor = float(sec.block_size) / 2.0 / float(sec.quantization_range)

        partial_bucket_meta_size = sec.partial_bucket_count * 4
        with open(file_path, 'rb') as f:
            f.seek(offset)
            partial_bucket_sizes = f.read(partial_bucket_meta_size)
        offset += partial_bucket_meta_size

        bucket_centers_size = sec.bucket_count * 3 * 4
        with open(file_path, 'rb') as f:
            f.seek(offset)
            bucket_centers = f.read(bucket_centers_size)
        offset += bucket_centers_size

        section_data_size = bytes_per_splat * sec.splat_capacity
        with open(file_path, 'rb') as f:
            f.seek(offset)
            splat_bytes = f.read(section_data_size)
        offset += section_data_size

        full_bucket_splats = sec.full_bucket_count * sec.bucket_capacity
        current_partial_bucket = sec.full_bucket_count
        current_partial_base = full_bucket_splats

        for j in range(sec.splat_count):
            bucket_idx = 0
            if sec.bucket_capacity > 0:
                if j < full_bucket_splats:
                    bucket_idx = j // sec.bucket_capacity
                else:
                    partial_idx = current_partial_bucket - sec.full_bucket_count
                    if partial_idx * 4 + 4 <= len(partial_bucket_sizes):
                        current_bucket_size = struct.unpack('<I', partial_bucket_sizes[partial_idx * 4:partial_idx * 4 + 4])[0]
                    else:
                        current_bucket_size = 0
                    if j >= current_partial_base + current_bucket_size:
                        current_partial_bucket += 1
                        current_partial_base += current_bucket_size
                    bucket_idx = current_partial_bucket

            boff = j * bytes_per_splat

            if main_header.compression_mode == 0:
                px = struct.unpack('<f', splat_bytes[boff:boff + 4])[0]
                py = struct.unpack('<f', splat_bytes[boff + 4:boff + 8])[0]
                pz = struct.unpack('<f', splat_bytes[boff + 8:boff + 12])[0]
            else:
                qx = struct.unpack('<H', splat_bytes[boff:boff + 2])[0]
                qy = struct.unpack('<H', splat_bytes[boff + 2:boff + 4])[0]
                qz = struct.unpack('<H', splat_bytes[boff + 4:boff + 6])[0]
                bcx = struct.unpack('<f', bucket_centers[bucket_idx * 12:bucket_idx * 12 + 4])[0]
                bcy = struct.unpack('<f', bucket_centers[bucket_idx * 12 + 4:bucket_idx * 12 + 8])[0]
                bcz = struct.unpack('<f', bucket_centers[bucket_idx * 12 + 8:bucket_idx * 12 + 12])[0]
                px = float((qx - sec.quantization_range) * position_scale_factor + bcx)
                py = float((qy - sec.quantization_range) * position_scale_factor + bcy)
                pz = float((qz - sec.quantization_range) * position_scale_factor + bcz)
            data.position[n, 0] = px
            data.position[n, 1] = py
            data.position[n, 2] = pz

            soff = boff + scale_start
            if main_header.compression_mode == 0:
                data.scale[n, 0] = codec.decode_splat_scale(struct.unpack('<f', splat_bytes[soff:soff + 4])[0])
                data.scale[n, 1] = codec.decode_splat_scale(struct.unpack('<f', splat_bytes[soff + 4:soff + 8])[0])
                data.scale[n, 2] = codec.decode_splat_scale(struct.unpack('<f', splat_bytes[soff + 8:soff + 12])[0])
            else:
                data.scale[n, 0] = codec.decode_splat_scale(codec.decode_float16(struct.unpack('<H', splat_bytes[soff:soff + 2])[0]))
                data.scale[n, 1] = codec.decode_splat_scale(codec.decode_float16(struct.unpack('<H', splat_bytes[soff + 2:soff + 4])[0]))
                data.scale[n, 2] = codec.decode_splat_scale(codec.decode_float16(struct.unpack('<H', splat_bytes[soff + 4:soff + 6])[0]))

            roff = boff + rotation_start
            if main_header.compression_mode == 0:
                rot0 = struct.unpack('<f', splat_bytes[roff:roff + 4])[0]
                rot1 = struct.unpack('<f', splat_bytes[roff + 4:roff + 8])[0]
                rot2 = struct.unpack('<f', splat_bytes[roff + 8:roff + 12])[0]
                rot3 = struct.unpack('<f', splat_bytes[roff + 12:roff + 16])[0]
            else:
                rot0 = codec.decode_float16(struct.unpack('<H', splat_bytes[roff:roff + 2])[0])
                rot1 = codec.decode_float16(struct.unpack('<H', splat_bytes[roff + 2:roff + 4])[0])
                rot2 = codec.decode_float16(struct.unpack('<H', splat_bytes[roff + 4:roff + 6])[0])
                rot3 = codec.decode_float16(struct.unpack('<H', splat_bytes[roff + 6:roff + 8])[0])
            data.rotation[n, 0] = codec.encode_splat_rotation(rot0)
            data.rotation[n, 1] = codec.encode_splat_rotation(rot1)
            data.rotation[n, 2] = codec.encode_splat_rotation(rot2)
            data.rotation[n, 3] = codec.encode_splat_rotation(rot3)

            coff = boff + color_start
            data.color[n, 0] = splat_bytes[boff + coff - boff] if coff == boff + color_start else 0
            data.color[n, 0] = splat_bytes[boff + color_start]
            data.color[n, 1] = splat_bytes[boff + color_start + 1]
            data.color[n, 2] = splat_bytes[boff + color_start + 2]
            data.color[n, 3] = splat_bytes[boff + color_start + 3]

            if main_header.sh_degree > 0:
                sh_indices = [
                    0, 3, 6, 1, 4, 7, 2, 5, 8,
                    9, 14, 19, 10, 15, 20, 11, 16, 21, 12, 17, 22, 13, 18, 23,
                    24, 31, 38, 25, 32, 39, 26, 33, 40, 27, 34, 41, 28, 35, 42, 29, 36, 43, 30, 37, 44
                ]
                sh_cnt = [0, 3, 8, 15][main_header.sh_degree] * 3
                hoff = boff + harmonics_start
                for k_idx in range(sh_cnt):
                    si = sh_indices[k_idx]
                    if main_header.compression_mode == 0:
                        so = hoff + si * 4
                        val = struct.unpack('<f', splat_bytes[so:so + 4])[0]
                        data.sh[n, k_idx] = codec.encode_splat_sh(val)
                    elif main_header.compression_mode == 1:
                        so = hoff + si * 2
                        val = codec.decode_float16(struct.unpack('<H', splat_bytes[so:so + 2])[0])
                        data.sh[n, k_idx] = codec.encode_splat_sh(val)
                    else:
                        so = hoff + si
                        raw = splat_bytes[so]
                        val = main_header.min_harmonics_value + (raw / 255.0) * (main_header.max_harmonics_value - main_header.min_harmonics_value)
                        data.sh[n, k_idx] = codec.encode_splat_sh(val)

            n += 1

    return main_header, data

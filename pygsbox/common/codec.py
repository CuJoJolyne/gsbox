import math
import struct
import numpy as np
from typing import Tuple, Optional, Union, List

COLOR_SCALE = 0.15
SH_C0 = 0.28209479177387814
DEG2RAD = math.pi / 180
RAD2DEG = 180 / math.pi
SQRT1_2 = 0.7071067811865476
SQRT2 = 1.4142135623730951
CMask = (1 << 9) - 1


def deg_to_rad(degrees: float) -> float:
    return degrees * DEG2RAD


def rad_to_deg(radians: float) -> float:
    return radians * RAD2DEG


def clip(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, val))


def clip_uint8(val: float) -> int:
    return int(max(0, min(255, val)))


def clip_uint16(val: float) -> int:
    return int(max(0, min(65535, val)))


def clip_float32(val: float) -> float:
    return float(float(max(-np.finfo(np.float32).max, min(np.finfo(np.float32).max, val))))  # type: ignore[arg-type]


def clip_uint8_round(val: float) -> int:
    if math.isnan(val) or math.isinf(val):
        return 0
    return int(max(0, min(255, round(val))))


def clip_int(val: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(max_val, val))


def float32_encode_uint16(val: float, min_val: float, max_val: float) -> int:
    f64 = round((val - min_val) / (max_val - min_val) * 65535.0)
    if f64 > 65535:
        f64 = 65535
    return int(f64)


def uint16_decode_float32(n: int, min_val: float, max_val: float) -> float:
    return n * (max_val - min_val) / 65535.0 + min_val


def encode_float32_to_bytes3(val: float) -> bytes:
    fixed32 = int(round(val * 4096))
    fixed32 = fixed32 & 0xFFFFFF
    return bytes([fixed32 & 0xFF, (fixed32 >> 8) & 0xFF, (fixed32 >> 16) & 0xFF])


def decode_bytes3_to_float32(b: bytes) -> float:
    fixed32 = b[0] | (b[1] << 8) | (b[2] << 16)
    if fixed32 & 0x800000:
        fixed32 |= -0x1000000
    return fixed32 / 4096.0


def encode_float32_to_byte(val: float) -> int:
    if val <= 0:
        return 0
    encoded = round((math.log(val) + 10.0) * 16.0)
    if encoded < 0:
        return 0
    elif encoded > 255:
        return 255
    return int(encoded)


def decode_byte_to_float32(encoded_byte: int) -> float:
    return math.exp(encoded_byte / 16.0 - 10.0)


def decode_float16(encoded: int) -> float:
    sign_bit = (encoded >> 15) & 1
    exponent = (encoded >> 10) & 0x1f
    mantissa = encoded & 0x3ff

    if exponent == 0:
        if mantissa == 0:
            return 0.0
        m = mantissa
        exp = -14
        while (m & 0x400) == 0:
            m <<= 1
            exp -= 1
        m &= 0x3ff
        final_exp = exp + 127
        final_mantissa = m << 13
        bits = (sign_bit << 31) | (final_exp << 23) | final_mantissa
        return float(struct.unpack('f', struct.pack('I', bits))[0])

    if exponent == 0x1f:
        if mantissa == 0:
            return float(-np.finfo(np.float32).max) if sign_bit == 1 else float(np.finfo(np.float32).max)
        return float('nan')

    final_exp = exponent - 15 + 127
    final_mantissa = mantissa << 13
    bits = (sign_bit << 31) | (final_exp << 23) | final_mantissa
    return float(struct.unpack('f', struct.pack('I', bits))[0])


def spz_encode_position(val: float) -> bytes:
    return encode_float32_to_bytes3(val)


def spz_decode_position(b: bytes, fractional_bits: int = 12) -> float:
    scale = 1.0 / (1 << fractional_bits)
    fixed32 = b[0] | (b[1] << 8) | (b[2] << 16)
    if fixed32 & 0x800000:
        fixed32 |= -0x1000000
    return clip_float32(fixed32 * scale)


def spz_encode_scale(val: float) -> int:
    return clip_uint8_round((val + 10.0) * 16.0)


def spz_decode_scale(val: int) -> float:
    return val / 16.0 - 10.0


def spz_encode_rotations_v3v4(rw: int, rx: int, ry: int, rz: int) -> bytes:
    r0 = rw / 128.0 - 1.0
    r1 = rx / 128.0 - 1.0
    r2 = ry / 128.0 - 1.0
    r3 = rz / 128.0 - 1.0
    qlen = math.sqrt(r0 * r0 + r1 * r1 + r2 * r2 + r3 * r3)
    rotation = [r1 / qlen, r2 / qlen, r3 / qlen, r0 / qlen]

    index = max(range(4), key=lambda i: abs(rotation[i]))
    if rotation[index] < 0:
        rotation = [-r for r in rotation]

    encoded = []
    for k in range(3, -1, -1):
        if k == index:
            continue
        sign = 1 if rotation[k] < 0 else 0
        val = abs(rotation[k]) / SQRT1_2
        mag = int(CMask * val + 0.5)
        encoded.append((sign << 9) | mag)

    packed = index << 30
    packed |= encoded[0]
    packed |= encoded[1] << 10
    packed |= encoded[2] << 20

    return struct.pack('<I', packed)


def spz_decode_rotations_v3v4(bs: bytes) -> Tuple[int, int, int, int]:
    comp = struct.unpack('<I', bs)[0]
    index = comp >> 30
    remaining = comp
    sum_squares = 0.0
    rotation = [0.0, 0.0, 0.0, 0.0]

    for i in range(3, -1, -1):
        if i != index:
            magnitude = remaining & CMask
            negbit = (remaining >> 9) & 0x1
            remaining = remaining >> 10

            rotation[i] = SQRT1_2 * (magnitude / CMask)
            if negbit == 1:
                rotation[i] = -rotation[i]

            sum_squares += rotation[i] * rotation[i]

    rotation[index] = math.sqrt(max(1.0 - sum_squares, 0))

    r0, r1, r2, r3 = rotation[3], rotation[0], rotation[1], rotation[2]
    return (
        clip_uint8(r0 * 128.0 + 128.0),
        clip_uint8(r1 * 128.0 + 128.0),
        clip_uint8(r2 * 128.0 + 128.0),
        clip_uint8(r3 * 128.0 + 128.0),
    )


def spz_encode_color(val: int) -> int:
    f_color = (val / 255.0 - 0.5) / SH_C0
    return clip_uint8_round(f_color * (COLOR_SCALE * 255.0) + (0.5 * 255.0))


def spz_decode_color(val: int) -> int:
    f_color = (val - (0.5 * 255.0)) / (COLOR_SCALE * 255.0)
    return clip_uint8((0.5 + SH_C0 * f_color) * 255.0)


def spz_encode_sh1(encode_sh_val: int) -> int:
    q = math.floor((encode_sh_val + 4.0) / 8.0) * 8.0
    return clip_uint8(q)


def spz_encode_sh23(encode_sh_val: int) -> int:
    q = math.floor((encode_sh_val + 8.0) / 16.0) * 16.0
    return clip_uint8(q)


def encode_splat_scale(val: float) -> float:
    return clip_float32(math.exp(val))


def decode_splat_scale(encoded_val: float) -> float:
    return clip_float32(math.log(encoded_val))


def encode_splat_color(val: float) -> int:
    return clip_uint8((0.5 + SH_C0 * val) * 255.0)


def decode_splat_color(val: int) -> float:
    return clip_float32((val / 255.0 - 0.5) / SH_C0)


def encode_splat_opacity_f32(val: int) -> float:
    v = decode_splat_opacity(val)
    return 1.0 / (1.0 + math.exp(-v))


def encode_splat_opacity(val: float) -> int:
    return clip_uint8((1.0 / (1.0 + math.exp(-val))) * 255.0)


def decode_splat_opacity(val: int) -> float:
    v = val / 255.0
    if v >= 1.0:
        return float(np.finfo(np.float32).max)
    if v <= 0.0:
        return float(-np.finfo(np.float32).max)
    return clip_float32(-math.log((1.0 / v) - 1.0))


def encode_splat_rotation(val: float) -> int:
    return clip_uint8(val * 128.0 + 128.0)


def decode_splat_rotation(val: int) -> float:
    return (val - 128.0) / 128.0


def encode_splat_sh(val: float) -> int:
    return clip_uint8(round(val * 128.0) + 128.0)


def decode_splat_sh(val: int) -> float:
    return (val - 128.0) / 128.0


def encode_spx_position_uint24(val: float) -> bytes:
    fixed32 = int(round(val * 4096.0))
    return bytes([fixed32 & 0xFF, (fixed32 >> 8) & 0xFF, (fixed32 >> 16) & 0xFF])


def decode_spx_position_uint24(b0: int, b1: int, b2: int) -> float:
    i32 = b0 | (b1 << 8) | (b2 << 16)
    if i32 & 0x800000:
        i32 |= -0x1000000
    return i32 / 4096.0


def encode_spx_scale(val: float) -> int:
    return clip_uint8_round((val + 10.0) * 16.0)


def decode_spx_scale(val: int) -> float:
    return val / 16.0 - 10.0


def encode_spx_sh(encode_sh_val: int) -> int:
    q = math.floor((encode_sh_val + 4.0) / 8.0) * 8.0
    return clip_uint8(q)


def decode_spx_rotations(rx: int, ry: int, rz: int) -> Tuple[int, int, int, int]:
    r1 = rx / 128.0 - 1.0
    r2 = ry / 128.0 - 1.0
    r3 = rz / 128.0 - 1.0
    r0 = math.sqrt(max(0.0, 1.0 - (r1 * r1 + r2 * r2 + r3 * r3)))
    return (
        clip_uint8(r0 * 128.0 + 128.0),
        clip_uint8(r1 * 128.0 + 128.0),
        clip_uint8(r2 * 128.0 + 128.0),
        clip_uint8(r3 * 128.0 + 128.0),
    )


def spz_encode_rotations(rw: int, rx: int, ry: int, rz: int) -> bytes:
    r0 = rw / 128.0 - 1.0
    r1 = rx / 128.0 - 1.0
    r2 = ry / 128.0 - 1.0
    r3 = rz / 128.0 - 1.0
    qlen = math.sqrt(r0 * r0 + r1 * r1 + r2 * r2 + r3 * r3)
    r0 /= qlen
    r1 /= qlen
    r2 /= qlen
    r3 /= qlen
    idx = max(range(4), key=lambda i: abs([r0, r1, r2, r3][i]))
    others = [r0, r1, r2, r3]
    del others[idx]
    result = []
    for r in others:
        v = abs(r) / SQRT1_2
        result.append(clip_uint8(round(v * 255.0)))
    return bytes(result)


def spz_decode_rotations(b0: int, b1: int, b2: int) -> Tuple[int, int, int, int]:
    r1 = b0 / 255.0 * SQRT1_2
    r2 = b1 / 255.0 * SQRT1_2
    r3 = b2 / 255.0 * SQRT1_2
    r0 = math.sqrt(max(0.0, 1.0 - r1 * r1 - r2 * r2 - r3 * r3))
    return (
        clip_uint8(r0 * 128.0 + 128.0),
        clip_uint8(r1 * 128.0 + 128.0),
        clip_uint8(r2 * 128.0 + 128.0),
        clip_uint8(r3 * 128.0 + 128.0),
    )


def sog_encode_rotation(val: float) -> int:
    return clip_uint8((val / SQRT2 + 0.5) * 255.0)


def sog_decode_rotation(val: int) -> float:
    return clip_float32((val / 255.0 - 0.5) * SQRT2)


def sog_encode_rotations(rw: int, rx: int, ry: int, rz: int) -> Tuple[int, int, int, int]:
    quats = normalize_rotations_float64(rw, rx, ry, rz)
    index = max(range(4), key=lambda i: abs(quats[i]))
    if quats[index] < 0:
        quats = [-q for q in quats]

    a = index + 252

    if index == 0:
        r, g, b = sog_encode_rotation(quats[1]), sog_encode_rotation(quats[2]), sog_encode_rotation(quats[3])
    elif index == 1:
        r, g, b = sog_encode_rotation(quats[0]), sog_encode_rotation(quats[2]), sog_encode_rotation(quats[3])
    elif index == 2:
        r, g, b = sog_encode_rotation(quats[0]), sog_encode_rotation(quats[1]), sog_encode_rotation(quats[3])
    else:
        r, g, b = sog_encode_rotation(quats[0]), sog_encode_rotation(quats[1]), sog_encode_rotation(quats[2])

    return r, g, b, a


def sog_decode_rotations(r0: int, r1: int, r2: int, ri: int) -> Tuple[int, int, int, int]:
    r0_f = sog_decode_rotation(r0)
    r1_f = sog_decode_rotation(r1)
    r2_f = sog_decode_rotation(r2)
    ri_f = clip_float32(math.sqrt(max(0, 1.0 - r0_f * r0_f - r1_f * r1_f - r2_f * r2_f)))
    idx = ri - 252

    if idx == 0:
        return encode_splat_rotations4(ri_f, r0_f, r1_f, r2_f)
    elif idx == 1:
        return encode_splat_rotations4(r0_f, ri_f, r1_f, r2_f)
    elif idx == 2:
        return encode_splat_rotations4(r0_f, r1_f, ri_f, r2_f)
    else:
        return encode_splat_rotations4(r0_f, r1_f, r2_f, ri_f)


def normalize_rotations_float64(rw: int, rx: int, ry: int, rz: int) -> list:
    r0 = rw / 128.0 - 1.0
    r1 = rx / 128.0 - 1.0
    r2 = ry / 128.0 - 1.0
    r3 = rz / 128.0 - 1.0
    qlen = math.sqrt(r0 * r0 + r1 * r1 + r2 * r2 + r3 * r3)
    return [r0 / qlen, r1 / qlen, r2 / qlen, r3 / qlen]


def encode_splat_rotations4(r0: float, r1: float, r2: float, r3: float) -> Tuple[int, int, int, int]:
    return (
        encode_splat_rotation(r0),
        encode_splat_rotation(r1),
        encode_splat_rotation(r2),
        encode_splat_rotation(r3),
    )


def encode_log(value: float, times: int = 1) -> float:
    if times < 1:
        return value
    log_val = clip_float32(math.log(abs(value) + 1.0))
    if value < 0:
        log_val = -log_val
    if times > 1:
        return encode_log(log_val, times - 1)
    return log_val


def decode_log(encoded: float, times: int = 1) -> float:
    if times < 1:
        return encoded
    original = clip_float32(math.exp(abs(encoded)) - 1.0)
    if encoded < 0:
        original = -original
    if times > 1:
        return decode_log(original, times - 1)
    return original


def sog_encode_log(value: float) -> float:
    log_val = math.log(abs(value) + 1.0)
    if value < 0:
        log_val = -log_val
    return clip_float32(log_val)


def hash_bytes(bts: bytes, init_val: int = 53653) -> int:
    rs = init_val
    for b in bts:
        rs = ((rs * 33) ^ b) & 0xFFFFFFFF
    return rs

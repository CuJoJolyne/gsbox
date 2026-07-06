import numpy as np
from typing import Tuple, Optional
from . import splat_data
from ..common import codec


class Quaternion:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, w: float = 1.0):
        self.x = x
        self.y = y
        self.z = z
        self.w = w

    @classmethod
    def from_axis_angle(cls, axis: Tuple[float, float, float], angle: float) -> 'Quaternion':
        half_angle = angle / 2
        s = np.sin(half_angle)
        return cls(axis[0] * s, axis[1] * s, axis[2] * s, np.cos(half_angle))

    def length(self) -> float:
        return np.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2 + self.w ** 2)  # type: ignore[no-any-return]

    def normalize(self) -> 'Quaternion':
        l = self.length()
        if l == 0:
            return Quaternion(0, 0, 0, 1)
        return Quaternion(self.x / l, self.y / l, self.z / l, self.w / l)

    def premultiply(self, q: 'Quaternion') -> 'Quaternion':
        return self._multiply_quaternions(q, self)

    @staticmethod
    def _multiply_quaternions(a: 'Quaternion', b: 'Quaternion') -> 'Quaternion':
        qax, qay, qaz, qaw = a.x, a.y, a.z, a.w
        qbx, qby, qbz, qbw = b.x, b.y, b.z, b.w
        return Quaternion(
            qax * qbw + qaw * qbx + qay * qbz - qaz * qby,
            qay * qbw + qaw * qby + qaz * qbx - qax * qbz,
            qaz * qbw + qaw * qbz + qax * qby - qay * qbx,
            qaw * qbw - qax * qbx - qay * qby - qaz * qbz,
        )


class Vector3:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z

    def apply_quaternion(self, q: Quaternion) -> 'Vector3':
        x, y, z = self.x, self.y, self.z
        qx, qy, qz, qw = q.x, q.y, q.z, q.w

        ix = qw * x + qy * z - qz * y
        iy = qw * y + qz * x - qx * z
        iz = qw * z + qx * y - qy * x
        iw = -qx * x - qy * y - qz * z

        return Vector3(
            ix * qw + iw * -qx + iy * -qz - iz * -qy,
            iy * qw + iw * -qy + iz * -qx - ix * -qz,
            iz * qw + iw * -qz + ix * -qy - iy * -qx,
        )


def translate(data: splat_data.SplatData, tx: float, ty: float, tz: float):
    """Translate all positions."""
    if tx == 0 and ty == 0 and tz == 0:
        return
    data.position[:, 0] += tx
    data.position[:, 1] += ty
    data.position[:, 2] += tz


def scale(data: splat_data.SplatData, factor: float):
    """Scale positions and adjust scales."""
    if factor == 1.0:
        return

    data.position *= factor

    encoded_scales = np.log(data.scale.astype(np.float64) + 1e-10)
    encoded_scales *= factor
    data.scale = np.exp(encoded_scales).astype(np.float32)
    data.scale = np.clip(data.scale, -np.finfo(np.float32).max, np.finfo(np.float32).max)


def rotate(data: splat_data.SplatData, degree_x: float, degree_y: float, degree_z: float):
    """Rotate positions and rotations."""
    if degree_x == 0 and degree_y == 0 and degree_z == 0:
        return

    qx = Quaternion.from_axis_angle((1, 0, 0), codec.deg_to_rad(degree_x))
    qy = Quaternion.from_axis_angle((0, 1, 0), codec.deg_to_rad(degree_y))
    qz = Quaternion.from_axis_angle((0, 0, 1), codec.deg_to_rad(degree_z))

    q = Quaternion()
    if degree_x != 0:
        q = q.premultiply(qx)
    if degree_y != 0:
        q = q.premultiply(qy)
    if degree_z != 0:
        q = q.premultiply(qz)
    q = q.normalize()

    for i in range(data.count):
        v = Vector3(data.position[i, 0], data.position[i, 1], data.position[i, 2])
        v = v.apply_quaternion(q)
        data.position[i, 0] = codec.clip_float32(v.x)
        data.position[i, 1] = codec.clip_float32(v.y)
        data.position[i, 2] = codec.clip_float32(v.z)

        rw = codec.decode_splat_rotation(int(data.rotation[i, 0]))
        rx = codec.decode_splat_rotation(int(data.rotation[i, 1]))
        ry = codec.decode_splat_rotation(int(data.rotation[i, 2]))
        rz = codec.decode_splat_rotation(int(data.rotation[i, 3]))

        rot_q = Quaternion(rx, ry, rz, rw)
        if degree_x != 0:
            rot_q = rot_q.premultiply(qx)
        if degree_y != 0:
            rot_q = rot_q.premultiply(qy)
        if degree_z != 0:
            rot_q = rot_q.premultiply(qz)

        rw_new, rx_new, ry_new, rz_new = _normalize_rotations(
            codec.encode_splat_rotation(rot_q.w),
            codec.encode_splat_rotation(rot_q.x),
            codec.encode_splat_rotation(rot_q.y),
            codec.encode_splat_rotation(rot_q.z),
        )
        data.rotation[i, 0] = rw_new
        data.rotation[i, 1] = rx_new
        data.rotation[i, 2] = ry_new
        data.rotation[i, 3] = rz_new


def _normalize_rotations(rw: int, rx: int, ry: int, rz: int) -> Tuple[int, int, int, int]:
    r0 = rw / 128.0 - 1.0
    r1 = rx / 128.0 - 1.0
    r2 = ry / 128.0 - 1.0
    r3 = rz / 128.0 - 1.0

    if r0 < 0:
        r0, r1, r2, r3 = -r0, -r1, -r2, -r3

    qlen = np.sqrt(r0 ** 2 + r1 ** 2 + r2 ** 2 + r3 ** 2)
    return (
        codec.clip_uint8((r0 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r1 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r2 / qlen) * 128.0 + 128.0),
        codec.clip_uint8((r3 / qlen) * 128.0 + 128.0),
    )


def transform(data: splat_data.SplatData,
              rotate_angles: Optional[Tuple[float, float, float]] = None,
              scale_factor: Optional[float] = None,
              translate_offset: Optional[Tuple[float, float, float]] = None,
              order: str = "RST"):
    """Apply transformations in specified order."""
    order = order.upper()

    def apply_rotate():
        if rotate_angles:
            rotate(data, *rotate_angles)

    def apply_scale():
        if scale_factor and scale_factor != 1.0:
            scale(data, scale_factor)

    def apply_translate():
        if translate_offset:
            translate(data, *translate_offset)

    ops = {'R': apply_rotate, 'S': apply_scale, 'T': apply_translate}
    for op in order:
        if op in ops:
            ops[op]()

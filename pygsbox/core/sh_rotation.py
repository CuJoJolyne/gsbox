import numpy as np
from typing import List
from .transform import Quaternion

SQRT_CONSTANTS = [
    1.7724538509055159,
    3.5449077018110318,
    1.8667697690487452,
    1.7995314438367746,
    0.9461746957575601,
    0.71286941498884980,
    2.8514771318343115,
    1.0690167946369905,
    0.95807781462646310,
    1.2560185433482819,
    0.62640318944523560,
    1.5693726477704796,
    0.45762635705172900,
    1.97461426021041560,
    1.4144686524933879,
    0.64668725328613700,
    0.37371898020398300,
    1.7313518646992609,
    1.3582822826423007,
    1.2430820420671210,
    0.27967665360786520,
    0.5526989765845118,
    1.4303931158596191,
    1.5154030551547617,
    0.44079317621869580,
    1.84264868911665350,
]


class SHRotation:
    def __init__(self, q: Quaternion):
        m = _quaternion_to_rotation_matrix(q)

        self.band1 = np.array([
            [m[1, 1], m[1, 2], m[1, 0]],
            [m[2, 1], m[2, 2], m[2, 0]],
            [m[0, 1], m[0, 2], m[0, 0]],
        ], dtype=np.float64)

        self.band2 = np.zeros((5, 5), dtype=np.float64)
        self.band2[0, 0] = -SQRT_CONSTANTS[11] * m[1, 0] * m[0, 0] + SQRT_CONSTANTS[12] * m[1, 2] * m[0, 2] - SQRT_CONSTANTS[11] * m[1, 1] * m[0, 1]
        self.band2[0, 1] = SQRT_CONSTANTS[13] * m[1, 0] * m[1, 2] + SQRT_CONSTANTS[13] * m[0, 0] * m[0, 2]
        self.band2[0, 2] = SQRT_CONSTANTS[14] * m[1, 0] * m[2, 0] + SQRT_CONSTANTS[14] * m[0, 0] * m[2, 2] + SQRT_CONSTANTS[14] * m[1, 1] * m[2, 1]
        self.band2[0, 3] = SQRT_CONSTANTS[13] * m[1, 0] * m[0, 1] + SQRT_CONSTANTS[13] * m[0, 0] * m[0, 1]
        self.band2[0, 4] = -SQRT_CONSTANTS[11] * m[0, 0] * m[1, 0] + SQRT_CONSTANTS[12] * m[0, 2] * m[1, 2] - SQRT_CONSTANTS[11] * m[0, 1] * m[1, 1]

        self.band2[1, 0] = -SQRT_CONSTANTS[11] * m[0, 0] * m[1, 2] - SQRT_CONSTANTS[11] * m[0, 2] * m[1, 0]
        self.band2[1, 1] = m[1, 0] * m[0, 0] - m[1, 1] * m[0, 1]
        self.band2[1, 2] = SQRT_CONSTANTS[15] * m[0, 0] * m[2, 2] + SQRT_CONSTANTS[15] * m[0, 2] * m[2, 0] + SQRT_CONSTANTS[15] * m[0, 1] * m[2, 1]
        self.band2[1, 3] = m[1, 0] * m[1, 0] - m[1, 1] * m[1, 1]
        self.band2[1, 4] = -SQRT_CONSTANTS[11] * m[1, 0] * m[0, 2] - SQRT_CONSTANTS[11] * m[1, 2] * m[0, 0]

        self.band2[2, 0] = SQRT_CONSTANTS[16] * m[0, 2] * m[2, 0] + SQRT_CONSTANTS[16] * m[0, 0] * m[2, 2] + SQRT_CONSTANTS[16] * m[0, 1] * m[2, 1]
        self.band2[2, 1] = SQRT_CONSTANTS[17] * m[1, 0] * m[2, 2] + SQRT_CONSTANTS[17] * m[1, 2] * m[2, 0] + SQRT_CONSTANTS[17] * m[1, 1] * m[2, 1]
        self.band2[2, 2] = m[2, 0] * m[2, 0] + m[2, 2] * m[2, 2] - m[2, 1] * m[2, 1]
        self.band2[2, 3] = SQRT_CONSTANTS[17] * m[1, 1] * m[2, 0] + SQRT_CONSTANTS[17] * m[1, 0] * m[2, 2] + SQRT_CONSTANTS[17] * m[1, 1] * m[2, 1]
        self.band2[2, 4] = SQRT_CONSTANTS[16] * m[0, 0] * m[2, 2] + SQRT_CONSTANTS[16] * m[0, 2] * m[2, 0] + SQRT_CONSTANTS[16] * m[0, 1] * m[2, 1]

        self.band2[3, 0] = -SQRT_CONSTANTS[11] * m[1, 0] * m[0, 2] - SQRT_CONSTANTS[11] * m[1, 2] * m[0, 0]
        self.band2[3, 1] = m[1, 0] * m[1, 0] - m[1, 2] * m[1, 2]
        self.band2[3, 2] = SQRT_CONSTANTS[15] * m[1, 0] * m[2, 2] + SQRT_CONSTANTS[15] * m[1, 2] * m[2, 0] + SQRT_CONSTANTS[15] * m[1, 1] * m[2, 1]
        self.band2[3, 3] = m[0, 0] * m[0, 0] - m[0, 2] * m[0, 2]
        self.band2[3, 4] = -SQRT_CONSTANTS[11] * m[0, 0] * m[1, 2] - SQRT_CONSTANTS[11] * m[0, 2] * m[1, 0]

        self.band2[4, 0] = -SQRT_CONSTANTS[11] * m[1, 1] * m[0, 0] + SQRT_CONSTANTS[12] * m[1, 2] * m[0, 2] - SQRT_CONSTANTS[11] * m[1, 2] * m[0, 1]
        self.band2[4, 1] = SQRT_CONSTANTS[13] * m[1, 2] * m[0, 0] + SQRT_CONSTANTS[13] * m[1, 0] * m[0, 2]
        self.band2[4, 2] = SQRT_CONSTANTS[14] * m[1, 2] * m[2, 2] + SQRT_CONSTANTS[14] * m[1, 0] * m[2, 0] + SQRT_CONSTANTS[14] * m[1, 1] * m[2, 1]
        self.band2[4, 3] = SQRT_CONSTANTS[13] * m[1, 2] * m[1, 0] + SQRT_CONSTANTS[13] * m[1, 0] * m[1, 2]
        self.band2[4, 4] = -SQRT_CONSTANTS[11] * m[0, 1] * m[1, 0] + SQRT_CONSTANTS[12] * m[0, 2] * m[1, 2] - SQRT_CONSTANTS[11] * m[0, 2] * m[1, 1]

        self.band3 = np.zeros((7, 7), dtype=np.float64)

    def apply(self, sh: List[float], band: int = 1):
        """Apply SH rotation to coefficients."""
        if band == 1 and len(sh) >= 3:
            result = self._apply_band(sh[:3], self.band1)
            sh[:3] = result
        elif band == 2 and len(sh) >= 5:
            result = self._apply_band(sh[:5], self.band2)
            sh[:5] = result
        elif band == 3 and len(sh) >= 7:
            result = self._apply_band(sh[:7], self.band3)
            sh[:7] = result

    def _apply_band(self, sh: List[float], matrix: np.ndarray) -> List[float]:
        result = [0.0] * len(sh)
        for i in range(len(sh)):
            for j in range(len(sh)):
                result[i] += sh[j] * matrix[i, j]
        return result


def _quaternion_to_rotation_matrix(q: Quaternion) -> np.ndarray:
    """Convert quaternion to 3x3 rotation matrix."""
    x, y, z, w = q.x, q.y, q.z, q.w

    len_sq = x * x + y * y + z * z + w * w
    if len_sq > 0:
        len_inv = 1.0 / np.sqrt(len_sq)
        x *= len_inv
        y *= len_inv
        z *= len_inv
        w *= len_inv

    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    m = np.array([
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
    ], dtype=np.float64)

    return m

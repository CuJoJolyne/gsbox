import math
import numpy as np
from typing import Tuple, Optional, Dict, List
from ..core.splat_data import SplatData
from ..common import codec

GRID_SIZE_FACTOR = 2.5
BASE_MERGE_THRESHOLD = -3.0
SCALE_MIN_RATIO = 0.5
SCALE_MAX_RATIO = 3.0
BLOCK_SIZE = 128.0
INV_BLOCK = 1.0 / BLOCK_SIZE
ALPHA_MIN = 20


def _fast_opacity(alpha_uint8: int) -> float:
    if alpha_uint8 <= 2:
        return 0.001
    if alpha_uint8 >= 253:
        return 0.999
    return codec.encode_splat_opacity_f32(alpha_uint8)


def _quat_to_mat3(w, x, y, z):
    xx, yy, zz = x * x, y * y, z * z
    return np.array([
        [1 - 2 * (yy + zz), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (xx + zz), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (xx + yy)],
    ], dtype=np.float32)


def _normalize_quat(rw, rx, ry, rz):
    q = np.array([rw, rx, ry, rz], dtype=np.float64)
    q_len = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    if q_len == 0:
        return 1.0, 0.0, 0.0, 0.0
    return (q / q_len)


def _eigen_decomp(A: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    try:
        vals, vecs = np.linalg.eigh(A.astype(np.float64))
        idx = np.argsort(-vals)
        return vals[idx].astype(np.float32), vecs[:, idx].astype(np.float32)
    except Exception:
        return np.array([1.0, 1.0, 1.0], dtype=np.float32), np.eye(3, dtype=np.float32)


def _mat_to_quat(m: np.ndarray) -> Tuple[float, float, float, float]:
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2.0
        return (
            0.25 * s,
            (m[2, 1] - m[1, 2]) / s,
            (m[0, 2] - m[2, 0]) / s,
            (m[1, 0] - m[0, 1]) / s,
        )
    return 1.0, 0.0, 0.0, 0.0


def _safe_log_sqrt(v: float) -> float:
    if v < 1e-9:
        v = 1e-9
    return math.log(math.sqrt(v))


def _outer(d: np.ndarray) -> np.ndarray:
    return np.outer(d, d).astype(np.float32)


def _build_sigma(scale_xyz: np.ndarray, quat_n: np.ndarray) -> np.ndarray:
    w, x, y, z = float(quat_n[3]), float(quat_n[0]), float(quat_n[1]), float(quat_n[2])
    R = _quat_to_mat3(w, x, y, z)
    D = np.diag(scale_xyz * scale_xyz)
    return R @ D @ R.T  # type: ignore[no-any-return]


def _merge_two(pos_a, pos_b, color_a, color_b, scale_a, scale_b, rot_a, rot_b,
               imp_a, imp_b):
    total = imp_a + imp_b
    if total < 1e-6:
        return pos_a, color_a, scale_a, rot_a, imp_a

    inv_total = 1.0 / total
    pos_out = (pos_a * imp_a + pos_b * imp_b) * inv_total
    color_out = (color_a.astype(np.float32) * imp_a + color_b.astype(np.float32) * imp_b) * inv_total

    exp_a = np.exp(scale_a.astype(np.float64))
    exp_b = np.exp(scale_b.astype(np.float64))

    qn_a = _normalize_quat(*rot_a[[0, 1, 2, 3]])
    qn_b = _normalize_quat(*rot_b[[0, 1, 2, 3]])

    sigma_a = _build_sigma(exp_a, np.array(qn_a, dtype=np.float64))
    sigma_b = _build_sigma(exp_b, np.array(qn_b, dtype=np.float64))

    da = pos_a - pos_out
    db = pos_b - pos_out

    sigma = imp_a * sigma_a + imp_b * sigma_b + imp_a * _outer(da) + imp_b * _outer(db)
    sigma = sigma * inv_total

    vals, vecs = _eigen_decomp(sigma)
    scale_out = np.array([_safe_log_sqrt(vals[0]), _safe_log_sqrt(vals[1]), _safe_log_sqrt(vals[2])], dtype=np.float32)

    qw, qx, qy, qz = _mat_to_quat(vecs)
    rot_out = np.array([
        codec.encode_splat_rotation(qx),
        codec.encode_splat_rotation(qy),
        codec.encode_splat_rotation(qz),
        codec.encode_splat_rotation(qw),
    ], dtype=np.uint8)

    return pos_out, color_out.astype(np.uint8), scale_out.astype(np.float32), rot_out, imp_a


def _similarity(pos_a, pos_b, color_a, color_b, exp_a, exp_b):
    d_pos = pos_a - pos_b
    dist_sq = float(np.dot(d_pos, d_pos))

    ca = color_a.astype(np.int32)
    cb = color_b.astype(np.int32)
    dr = float(ca[0] - cb[0]) / 255.0
    dg = float(ca[1] - cb[1]) / 255.0
    db = float(ca[2] - cb[2]) / 255.0
    color_sq = dr * dr + dg * dg + db * db

    scale_diff = abs(exp_a[0] - exp_b[0])
    scale_sum = exp_a[0] + exp_b[0] + 1e-6

    return -(dist_sq + color_sq * 0.5 + scale_diff / scale_sum * 2.0)


def mask_to_bool(size: int, indices: np.ndarray) -> np.ndarray:
    mask = np.zeros(size, dtype=bool)
    mask[indices] = True
    return mask


def simplify(data: SplatData, grid_size_factor: float = GRID_SIZE_FACTOR,
             merge_threshold: float = BASE_MERGE_THRESHOLD,
             block_size: float = BLOCK_SIZE) -> SplatData:
    if data.count == 0:
        return data

    mask_alpha = data.color[:, 3] >= ALPHA_MIN
    if not np.any(mask_alpha):
        return SplatData(0)

    valid = data.subset(mask_alpha)
    n = valid.count

    exp_scales = np.exp(valid.scale.astype(np.float64)).astype(np.float32)
    alphas_f32 = np.empty(n, dtype=np.float32)
    for i in range(n):
        alphas_f32[i] = _fast_opacity(int(valid.color[i, 3]))

    volumes = exp_scales[:, 0] * exp_scales[:, 1] * exp_scales[:, 2] * alphas_f32
    avg_scale = float(np.mean(exp_scales))

    order = np.argsort(-volumes)
    valid = valid.subset(mask_to_bool(valid.count, order))

    grid_size = float(avg_scale * grid_size_factor)
    if grid_size < 1e-3:
        grid_size = 0.01

    block_map: Dict[Tuple[int, int, int], List[int]] = {}
    positions = valid.position
    inv_block = 1.0 / block_size
    block_keys = np.floor(positions * inv_block).astype(np.int32)
    for i in range(valid.count):
        k = (int(block_keys[i, 0]), int(block_keys[i, 1]), int(block_keys[i, 2]))
        if k not in block_map:
            block_map[k] = []
        block_map[k].append(i)

    out_counts = []
    out_positions = []
    out_colors = []
    out_scales = []
    out_rotations = []

    for indices in block_map.values():
        indices_arr = np.array(indices, dtype=np.int32)
        chunk_n = len(indices_arr)
        if chunk_n < 2:
            out_counts.extend(indices)
            continue

        chunk_pos = positions[indices_arr]
        chunk_colors = valid.color[indices_arr]
        chunk_scales = valid.scale[indices_arr]
        chunk_rotations = valid.rotation[indices_arr]
        chunk_volumes = volumes[indices_arr]
        chunk_exp = exp_scales[indices_arr]

        inv_grid = 1.0 / grid_size
        grid_keys = np.floor(chunk_pos * inv_grid).astype(np.int32)

        cell_map: Dict[Tuple[int, int, int], List[int]] = {}
        for j in range(chunk_n):
            k = (int(grid_keys[j, 0]), int(grid_keys[j, 1]), int(grid_keys[j, 2]))
            if k not in cell_map:
                cell_map[k] = []
            cell_map[k].append(j)

        used = np.zeros(chunk_n, dtype=bool)
        kept = []
        merged = []

        for j in range(chunk_n):
            if used[j]:
                continue
            cx, cy, cz = int(grid_keys[j, 0]), int(grid_keys[j, 1]), int(grid_keys[j, 2])
            best_score = -1000000.0
            best_idx = -1

            for dz in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nk = (cx + dx, cy + dy, cz + dz)
                        if nk not in cell_map:
                            continue
                        for other in cell_map[nk]:
                            if other == j or used[other]:
                                continue
                            ratio = chunk_exp[j, 0] / (chunk_exp[other, 0] + 1e-6)
                            if ratio < SCALE_MIN_RATIO or ratio > SCALE_MAX_RATIO:
                                continue
                            score = _similarity(
                                chunk_pos[j], chunk_pos[other],
                                chunk_colors[j], chunk_colors[other],
                                chunk_exp[j], chunk_exp[other],
                            )
                            if score > best_score:
                                best_score = score
                                best_idx = other

            if best_idx >= 0 and best_score > merge_threshold:
                pos_o, col_o, sc_o, rot_o, imp_o = _merge_two(
                    chunk_pos[j], chunk_pos[best_idx],
                    chunk_colors[j], chunk_colors[best_idx],
                    chunk_scales[j], chunk_scales[best_idx],
                    chunk_rotations[j], chunk_rotations[best_idx],
                    chunk_volumes[j], chunk_volumes[best_idx],
                )
                merged.append((pos_o, col_o, sc_o, rot_o))
                used[j] = True
                used[best_idx] = True
            else:
                kept.append(j)

        for k_idx in kept:
            out_counts.append(indices_arr[k_idx])
        for pos_o, col_o, sc_o, rot_o in merged:
            out_positions.append(pos_o)
            out_colors.append(col_o)
            out_scales.append(sc_o)
            out_rotations.append(rot_o)

    kept_indices = np.array(out_counts, dtype=np.int32) if out_counts else np.zeros(0, dtype=np.int32)
    result = valid.subset(np.zeros(valid.count, dtype=bool))
    result.count = 0

    parts = []
    if len(kept_indices) > 0:
        mask = np.zeros(valid.count, dtype=bool)
        mask[kept_indices] = True
        parts.append(valid.subset(mask))

    if out_positions:
        merged_data = SplatData(len(out_positions))
        merged_data.position = np.array(out_positions, dtype=np.float32)
        merged_data.color = np.array(out_colors, dtype=np.uint8)
        merged_data.scale = np.array(out_scales, dtype=np.float32)
        merged_data.rotation = np.array(out_rotations, dtype=np.uint8)
        parts.append(merged_data)

    if not parts:
        return SplatData(0)

    result = parts[0]
    for p in parts[1:]:
        result.append(p)
    return result

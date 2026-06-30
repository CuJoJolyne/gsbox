import os
from ..common import codec
from ..core.transform import Quaternion, Vector3


def _rotate_vertex(x: float, y: float, z: float,
                   dx: float, dy: float, dz: float) -> tuple:
    qx = Quaternion.from_axis_angle((1, 0, 0), codec.deg_to_rad(dx))
    qy = Quaternion.from_axis_angle((0, 1, 0), codec.deg_to_rad(dy))
    qz = Quaternion.from_axis_angle((0, 0, 1), codec.deg_to_rad(dz))
    q = Quaternion()
    if dx != 0:
        q = q.premultiply(qx)
    if dy != 0:
        q = q.premultiply(qy)
    if dz != 0:
        q = q.premultiply(qz)
    q = q.normalize()
    v = Vector3(x, y, z).apply_quaternion(q)
    return codec.clip_float32(v.x), codec.clip_float32(v.y), codec.clip_float32(v.z)


def _transform_vertex(x: float, y: float, z: float,
                      degree_x: float, degree_y: float, degree_z: float,
                      scale_factor: float, tx: float, ty: float, tz: float,
                      order: str) -> tuple:

    def rotate():
        nonlocal x, y, z
        x, y, z = _rotate_vertex(x, y, z, degree_x, degree_y, degree_z)

    def translate():
        nonlocal x, y, z
        x, y, z = x + tx, y + ty, z + tz

    def scale_vertex():
        nonlocal x, y, z
        x, y, z = x * scale_factor, y * scale_factor, z * scale_factor

    ops = {
        "rts": [rotate, translate, scale_vertex],
        "srt": [scale_vertex, rotate, translate],
        "str": [scale_vertex, translate, rotate],
        "trs": [translate, rotate, scale_vertex],
        "tsr": [translate, scale_vertex, rotate],
        "rst": [rotate, scale_vertex, translate],
    }
    for op in ops.get(order, ops["rst"]):
        op()
    return x, y, z


def obj_transform(src_path: str, dst_path: str,
                  degree_x: float = 0.0, degree_y: float = 0.0, degree_z: float = 0.0,
                  scale_factor: float = 1.0,
                  tx: float = 0.0, ty: float = 0.0, tz: float = 0.0,
                  order: str = "rst"):
    os.makedirs(os.path.dirname(dst_path) or '.', exist_ok=True)

    has_rotate = degree_x != 0 or degree_y != 0 or degree_z != 0
    has_scale = scale_factor != 1.0
    has_translate = tx != 0 or ty != 0 or tz != 0

    has_transform = has_rotate or has_scale or has_translate

    with open(src_path, 'r', encoding='utf-8') as src:
        with open(dst_path, 'w', encoding='utf-8') as dst:
            for line in src:
                stripped = line.rstrip('\n\r')
                if has_transform and (stripped.startswith("v ") or stripped.startswith("v\t")):
                    parts = stripped.split()
                    if len(parts) >= 4:
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        nx, ny, nz = _transform_vertex(
                            x, y, z, degree_x, degree_y, degree_z,
                            scale_factor, tx, ty, tz, order
                        )
                        dst.write(f"v {nx:.6f} {ny:.6f} {nz:.6f}\n")
                        continue
                dst.write(stripped + "\n")

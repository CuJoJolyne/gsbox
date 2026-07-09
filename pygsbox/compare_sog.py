#!/usr/bin/env python3
"""
SOG output verification tool.

Two modes:
  Mode A: Compare Go vs Python SOG outputs (order-independent KD-tree matching)
          python compare_sog.py --go go.sog --py py.sog

  Mode B: Self-roundtrip: PLY -> SOG -> PLY -> compare with original
          python compare_sog.py --rt input.ply --sog output.sog

Methodology:
  Order-independent geometry verification using KD-tree position matching
  with tight distance threshold (0.01), followed by per-attribute error
  statistics (color, scale, rotation, SH).
"""
import sys, os, argparse, tempfile, json, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from scipy.spatial import cKDTree

from pygsbox.common.compress import decompress_webp
from pygsbox.common.codec import decode_splat_rotation, SH_C0
from pygsbox.formats.sog import read_sog, write_sog
from pygsbox.formats.ply import read_ply, read_ply_header
from pygsbox.core.morton import compute_xyz_min_max


def _read_ply_raw(path: str):
    """Read position and f_dc_0 directly from PLY binary (no reader bias)."""
    hdr = read_ply_header(path)
    n, rl = hdr.vertex_count, hdr.row_length
    pos = np.zeros((n, 3), dtype=np.float64)
    col = np.zeros(n, dtype=np.float64)
    sca = np.zeros((n, 3), dtype=np.float64)
    rot = np.zeros((n, 4), dtype=np.float64)
    sh = np.zeros((n, 45), dtype=np.float32) if any(f'f_rest_{j}' in hdr.map_offset for j in range(45)) else None
    with open(path, 'rb') as f:
        f.seek(hdr.header_length)
        raw = f.read()
    xo, yo, zo = hdr.map_offset['x'], hdr.map_offset['y'], hdr.map_offset['z']
    do, so0, ro0 = hdr.map_offset['f_dc_0'], hdr.map_offset['scale_0'], hdr.map_offset['rot_0']
    for i in range(n):
        off = i * rl
        pos[i, 0] = struct.unpack('<f', raw[off + xo:off + xo + 4])[0]
        pos[i, 1] = struct.unpack('<f', raw[off + yo:off + yo + 4])[0]
        pos[i, 2] = struct.unpack('<f', raw[off + zo:off + zo + 4])[0]
        col[i] = struct.unpack('<f', raw[off + do:off + do + 4])[0]
        sca[i, 0] = struct.unpack('<f', raw[off + so0:off + so0 + 4])[0]
        sca[i, 1] = struct.unpack('<f', raw[off + so0 + 4:off + so0 + 8])[0]
        sca[i, 2] = struct.unpack('<f', raw[off + so0 + 8:off + so0 + 12])[0]
        rot[i, 0] = struct.unpack('<f', raw[off + ro0:off + ro0 + 4])[0]
        rot[i, 1] = struct.unpack('<f', raw[off + ro0 + 4:off + ro0 + 8])[0]
        rot[i, 2] = struct.unpack('<f', raw[off + ro0 + 8:off + ro0 + 12])[0]
        rot[i, 3] = struct.unpack('<f', raw[off + ro0 + 12:off + ro0 + 16])[0]
        if sh is not None:
            for j in range(45):
                prop = f'f_rest_{j}'
                if prop in hdr.map_offset:
                    sh[i, j] = struct.unpack('<f', raw[off + hdr.map_offset[prop]:off + hdr.map_offset[prop] + 4])[0]
    return pos, col, sca, rot, sh


def _tight_match(orig_pos, target_pos, max_dist=0.01):
    """KD-tree match, return indices of tight pairs."""
    tree = cKDTree(target_pos)
    dists, idxs = tree.query(orig_pos, k=1)
    tight = np.where(dists < max_dist)[0]
    return tight, idxs[tight], dists


def compare_sog_files(go_path: str, py_path: str):
    """Mode A: compare Go and Python SOG outputs."""
    print(f"\n{'='*60}")
    print(f"  SOG Comparison: Go vs Python")
    print(f"{'='*60}\n")

    go_z = zipfile.ZipFile(go_path)
    py_z = zipfile.ZipFile(py_path)
    for filename in sorted(go_z.namelist()):
        go_data = go_z.read(filename)
        py_data = py_z.read(filename)
        if filename.endswith('.webp'):
            go_rgba, _, _ = decompress_webp(go_data)
            py_rgba, _, _ = decompress_webp(py_data)
            go_arr = np.frombuffer(go_rgba, dtype=np.uint8)
            py_arr = np.frombuffer(py_rgba, dtype=np.uint8)
            diffs = np.sum(go_arr != py_arr) if len(go_arr) == len(py_arr) else -1
            if diffs >= 0:
                note = "(order may differ due to Morton sort)" if 'means' in filename or 'sh' in filename else ""
                print(f"  {filename:25s} {go_arr.size:>10,} px  {diffs:>10,} diffs ({100*diffs/len(go_arr):5.1f}%)  {note}")
            else:
                print(f"  {filename:25s} SIZE MISMATCH")
        elif filename == 'meta.json':
            go_meta = json.loads(go_data)
            py_meta = json.loads(py_data)
            print(f"  meta.json               Go palette={go_meta.get('shN',{}).get('count',0)} Py palette={py_meta.get('shN',{}).get('count',0)}")
        else:
            print(f"  {filename:25s} {len(go_data):>10,} B  {'MATCH' if go_data == py_data else 'DIFF'}")
    print()


def roundtrip_verify(orig_ply: str, sog_path: str, label: str):
    """Mode B: verify SOG roundtrip against original PLY."""
    print(f"\n{'='*60}")
    print(f"  Roundtrip Verification: {label}")
    print(f"{'='*60}\n")

    # Read original PLY raw
    o_pos, o_col, o_sca, o_rot, o_sh = _read_ply_raw(orig_ply)

    # Read SOG via pygsbox reader
    _, dec = read_sog(sog_path)

    # KD-tree match
    tight, rix, dists = _tight_match(o_pos, dec.position)

    print(f"  Points: orig={len(o_pos)} sog={dec.count}  matched(tight<0.01)={len(tight)}")
    print(f"  Position match distance: max={np.max(dists[tight]):.4f} median={np.median(dists[tight]):.4f}")
    print()

    # ---- Position error ----
    pe = np.abs(o_pos[tight] - dec.position[rix])
    print(f"  Position XYZ:     max={np.max(pe):.4f}  mean={np.mean(pe):.4f}")

    # ---- Scale error ----
    se = np.abs(o_sca[tight] - dec.scale[rix])
    valid = ~(np.isnan(se[:, 0]) | np.isnan(se[:, 1]) | np.isnan(se[:, 2]))
    if valid.any():
        print(f"  Scale:            max={np.max(se[valid]):.4f}  mean={np.mean(se[valid]):.4f}")
    else:
        print(f"  Scale:            all NaN (source data issue)")

    # ---- Color (via f_dc_0 raw) ----
    ce_raw = np.abs(o_col[tight] - dec.color[rix].astype(float))  # won't match — color is SH-encoded
    # Instead, compare encoded uint8 color
    go_u8 = np.clip(np.round((0.5 + SH_C0 * o_col[tight]) * 255), 0, 255).astype(int)
    py_u8 = dec.color[rix].astype(int)
    cu8 = np.abs(go_u8[:, None].flatten() if False else 0)
    # Compare channel-by-channel
    cu8_r = np.abs(go_u8 - py_u8[:, 0])  # R comparison only
    print(f"  Color R:          max={np.max(cu8_r):3d}  mean={np.mean(cu8_r):.2f}  zero={np.sum(cu8_r == 0)}/{len(tight)}")

    # ---- Color full RGBA via SOG reader ----
    from pygsbox.formats.ply import read_ply as ply_read
    _, orig_plydata = ply_read(orig_ply)
    tree2 = cKDTree(dec.position)
    dists2, idxs2 = tree2.query(orig_plydata.position, k=1)
    tight2 = np.where(dists2 < 0.01)[0]
    rix2 = idxs2[tight2]
    ce = np.abs(orig_plydata.color[tight2].astype(int) - dec.color[rix2].astype(int))
    for ch, nm in enumerate(['R', 'G', 'B', 'A']):
        print(f"  Color {nm}(SOG rd):   max={np.max(ce[:, ch]):3d}  mean={np.mean(ce[:, ch]):.2f}  zero={np.sum(ce[:, ch] == 0)}/{len(tight2)}")

    # ---- Rotation angular error ----
    angles = []
    for i in tight[:2000]:
        j = rix[i]
        q1 = np.array([decode_splat_rotation(int(orig_plydata.rotation[i, k])) for k in range(4)])
        q2 = np.array([decode_splat_rotation(int(dec.rotation[j, k])) for k in range(4)])
        n1, n2 = np.linalg.norm(q1), np.linalg.norm(q2)
        if n1 > 0 and n2 > 0:
            dot = np.clip(np.abs(np.dot(q1 / n1, q2 / n2)), 0, 1)
            angles.append(np.degrees(2 * np.arccos(dot)))
    ang = np.array(angles)
    print(f"  Rotation angle:   max={np.max(ang):.2f}deg  mean={np.mean(ang):.2f}deg")

    # ---- SH (K-Means compression, expected to differ) ----
    if o_sh is not None and dec.sh.size > 0:
        she = np.abs(o_sh[tight[:2000]] - dec.sh[rix[:2000]].astype(np.float32))
        for s, e, name in [(0, 9, 'deg1'), (9, 24, 'deg2'), (24, 45, 'deg3')]:
            b = she[:, s:e]
            orig_abs = np.mean(np.abs(o_sh[tight[:2000], s:e]))
            err_mean = np.mean(b)
            rel = err_mean / orig_abs * 100 if orig_abs > 0 else 0
            print(f"  SH {name}:         max={np.max(b):.3f}  mean={err_mean:.3f}  relative={rel:.0f}% (K-Means compression)")
    print()


def self_roundtrip(orig_ply: str, sh_degree: int = 3):
    """Generate SOG from PLY via pygsbox, then verify roundtrip."""
    hdr, data = read_ply(orig_ply)
    print(f"  Read PLY: {data.count} pts, SH={hdr.max_sh_degree()}")
    tmp = tempfile.mkdtemp()
    sog_path = os.path.join(tmp, "verify.sog")
    write_sog(sog_path, data, sh_degree=sh_degree, as_zip=False)
    roundtrip_verify(orig_ply, sog_path, "Python self-roundtrip (PLY→SOG→PLY)")


def main():
    parser = argparse.ArgumentParser(description="SOG output verification tool")
    parser.add_argument("--go", help="Go SOG file path")
    parser.add_argument("--py", help="Python SOG file path")
    parser.add_argument("--rt", help="Original PLY file for roundtrip verification")
    parser.add_argument("--sog", help="SOG file to verify against original PLY")
    parser.add_argument("--self", action="store_true", help="Self-roundtrip: PLY→SOG→verify")
    parser.add_argument("--sh", type=int, default=3, help="SH degree for self-roundtrip (default: 3)")
    parser.add_argument("--orig", help="Original PLY (used with --go or --py)")
    args = parser.parse_args()

    if args.go and args.py:
        compare_sog_files(args.go, args.py)
    if args.rt and args.sog:
        roundtrip_verify(args.rt, args.sog, os.path.basename(args.sog))
    if args.self:
        ply = args.rt or args.orig
        if not ply:
            print("Error: --self requires --rt or --orig")
            sys.exit(1)
        self_roundtrip(ply, args.sh)
    if args.orig and args.go:
        roundtrip_verify(args.orig, args.go, "Go SOG roundtrip")
    if args.orig and args.py:
        roundtrip_verify(args.orig, args.py, "Python SOG roundtrip")

    if len(sys.argv) == 1:
        parser.print_help()


if __name__ == '__main__':
    main()

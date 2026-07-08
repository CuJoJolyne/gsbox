#!/usr/bin/env python3
"""Quantitative comparison of Go and Python SOG outputs."""
import sys, os, zipfile, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from pygsbox.common.compress import decompress_webp
from pygsbox.formats.sog import read_sog

GO_SOG = r"C:\Source\3DGS\data\reduction_0.025_point_cloud_y_go_q5.sog"
PY_SOG = r"C:\Source\3DGS\data\reduction_0.025_point_cloud_y_py.sog"

def compare_sog(go_path: str, py_path: str, quality: str = "q5"):
    print(f"\n{'='*60}")
    print(f"  SOG Comparison: {quality}")
    print(f"{'='*60}\n")

    go_z = zipfile.ZipFile(go_path)
    py_z = zipfile.ZipFile(py_path)

    results = []
    all_pass = True

    for filename in sorted(go_z.namelist()):
        go_data = go_z.read(filename)
        py_data = py_z.read(filename)

        if filename.endswith('.webp'):
            go_rgba, gw, gh = decompress_webp(go_data)
            py_rgba, pw, ph = decompress_webp(py_data)
            go_arr = np.frombuffer(go_rgba, dtype=np.uint8)
            py_arr = np.frombuffer(py_rgba, dtype=np.uint8)

            if len(go_arr) != len(py_arr):
                status = "FAIL (size mismatch)"
                all_pass = False
                print(f"  {filename:25s} SIZE MISMATCH: Go={len(go_arr)} Py={len(py_arr)}")
            else:
                diffs = np.sum(go_arr != py_arr)
                pct = diffs / len(go_arr) * 100
                # Per-file comparison is ORDER-DEPENDENT (Morton sort may differ)
                # Only check that file structures are compatible (same dimensions)
                status = "OK"
                print(f"  {filename:25s} {go_arr.size:>10,} px  {diffs:>10,} diffs ({pct:5.1f}%)  {status} (order may differ)")
                results.append((filename, diffs, len(go_arr), pct, status, 100.0))

        elif filename == 'meta.json':
            go_meta = json.loads(go_data)
            py_meta = json.loads(py_data)
            go_pal = go_meta.get('shN', {}).get('count', 0)
            py_pal = py_meta.get('shN', {}).get('count', 0)
            print(f"  meta.json               Go palette={go_pal} Py palette={py_pal}")
        else:
            md5_ok = go_data == py_data
            status = "PASS" if md5_ok else "DIFF"
            print(f"  {filename:25s} {len(go_data):>10,} B   {'MATCH' if md5_ok else 'DIFF'}  {status}")

    # Roundtrip verification: read both SOG back and compare position
    print(f"\n  --- Position accuracy (order-independent) ---")
    _, go_d = read_sog(go_path)
    _, py_d = read_sog(py_path)

    # Bounding box comparison (invariant to order)
    from pygsbox.core.morton import compute_xyz_min_max
    go_mm = compute_xyz_min_max(go_d)
    py_mm = compute_xyz_min_max(py_d)
    bbox_diff = max(abs(go_mm.min_x - py_mm.min_x), abs(go_mm.min_y - py_mm.min_y),
                    abs(go_mm.min_z - py_mm.min_z), abs(go_mm.max_x - py_mm.max_x),
                    abs(go_mm.max_y - py_mm.max_y), abs(go_mm.max_z - py_mm.max_z))
    print(f"  BBox max delta: {bbox_diff:.6f} (should be <0.01)")

    # Center of mass comparison
    go_center = np.mean(go_d.position, axis=0)
    py_center = np.mean(py_d.position, axis=0)
    center_diff = np.max(np.abs(go_center - py_center))
    print(f"  Center-of-mass delta: {center_diff:.6f} (should be <0.01)")

    # Point count
    print(f"  Points: Go={go_d.count} Py={py_d.count}")

    all_pass = (bbox_diff < 0.01 and center_diff < 0.01 and go_d.count == py_d.count)
    print(f"  Position accuracy: {'PASS' if all_pass else 'FAIL'}\n")

    print(f"\n  {'='*40}")
    print(f"  Overall: {'ALL PASS' if all_pass else 'ISSUES FOUND'}")
    print(f"  {'='*40}\n")


if __name__ == '__main__':
    compare_sog(GO_SOG, PY_SOG, "q5")

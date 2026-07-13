#!/usr/bin/env python3
import sys
import os
import time
from typing import Optional, Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pygsbox.common import version
from pygsbox.common.file_utils import file_ext_name, is_net_file, read_remote_to_local
from pygsbox.common.progress import Progress, default_callback
from pygsbox.common.version_check import check_update
from pygsbox.formats import ply, splat, spx, spz, sog, ksplat, glb, obj
from pygsbox.advanced import simplify as simp_module, lod as lod_module, autocut
from pygsbox.core import splat_data, morton, transform


def usage():
    print(f"\npygsbox {version.VER}")
    print("Python implementation of gsbox for 3D Gaussian Splatting\n")
    print("Usage:")
    print("  pygsbox <command> [options]\n")
    print("Commands:")
    print("  convert        Auto-detect: any format to any format")
    print("  info           Display file information")
    print("  simplify       Voxel-based model simplification")
    print("  lod            Build LOD B-Tree tiles")
    print("  obj            Transform vertices in .obj file")
    print("  autocut        Auto LOD generation (simplify x5 + B-Tree)")
    print("  cut            Combine multiple LOD models into lod-meta.json")
    print("  check_update   Check for latest pygsbox release")
    print("  Shortcut commands (same as convert):")
    print("    p2s, ply2splat     p2z, ply2spz     p2g, ply2glb")
    print("    z2p, spz2ply       z2g, spz2glb     g2p, glb2ply\n")
    print("Options:")
    print("  -i,  --input <path>       Input file path (repeatable)")
    print("  -o,  --output <path>      Output file path")
    print("  -l,  --lod-level <int>    LOD level for input (repeatable, for cut)")
    print("  -sh, --shDegree <0-3>     SH degree for output (default: keep)")
    print("  -a,  --alpha <0-255>      Minimum alpha filter")
    print("  -rx, -ry, -rz <deg>       Rotation around X/Y/Z axis")
    print("  -s,  --scale <factor>     Uniform scaling factor")
    print("  -tx, -ty, -tz <val>       Translation offset")
    print("  -to, --transform-order    Transform order [RST,RTS,SRT,STR,TRS,TSR]")
    print("  -ov, --output-version <v> SPZ version (2/3/4) or SPX version (1/2/3)")
    print("  -bf, --block-format <id>  SPX block format ID (default: 220)")
    print("  -q,  --quality <1-9>      encoding quality (default: 5)")
    print("  -cs, --cut-size <int>     B-Tree leaf node size (default: 102400)")
    print("  -v,  --version            Show version")
    print("  -h,  --help               Show this help\n")
    print("Examples:")
    print("  pygsbox convert -i input.ply -o output.spz -sh 1")
    print("  pygsbox convert -i https://example.com/model.spz -o output.ply")
    print("  pygsbox info -i file.spx")
    print("  pygsbox autocut -i input.ply -o lod-meta.json")
    print("  pygsbox cut -i lod0.ply -l 0 -i lod1.ply -l 1 -o lod-meta.json")
    print()


def parse_args(argv) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in ('-h', '--help', 'help'):
            args['command'] = 'help'; return args
        elif a in ('-v', '--version', 'version'):
            args['command'] = 'version'; return args
        elif a in ('convert', 'ply2splat', 'p2s', 'splat2ply', 's2p',
                   'ply2ply', 'p2p', 'ply2spz', 'p2z', 'spz2ply', 'z2p',
                   'ply2glb', 'p2g', 'glb2ply', 'g2p', 'spz2glb', 'z2g',
                   'glb2spz', 'g2z'):
            cmd = a
            if cmd in ('p2s',): cmd = 'ply2splat'
            if cmd in ('s2p',): cmd = 'splat2ply'
            if cmd in ('p2p',): cmd = 'ply2ply'
            if cmd in ('p2z',): cmd = 'ply2spz'
            if cmd in ('z2p',): cmd = 'spz2ply'
            if cmd in ('p2g',): cmd = 'ply2glb'
            if cmd in ('g2p',): cmd = 'glb2ply'
            if cmd in ('z2g',): cmd = 'spz2glb'
            if cmd in ('g2z',): cmd = 'glb2spz'
            args['command'] = cmd
        elif a in ('info', 'simplify', 'lod', 'obj', 'autocut', 'check_update', 'cut'):
            args['command'] = a
        elif a in ('-i', '--input'):
            i += 1; val = argv[i] if i < len(argv) else ''; args.setdefault('inputs', []).append(val); args['input'] = val
        elif a in ('-l', '--lod-level'):
            i += 1; args.setdefault('lodLevels', []).append(int(argv[i]) if i < len(argv) else 0)
        elif a in ('-o', '--output'):
            i += 1; args['output'] = argv[i] if i < len(argv) else ''
        elif a in ('-rx', '--rotateX'):
            i += 1; args['rotateX'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-ry', '--rotateY'):
            i += 1; args['rotateY'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-rz', '--rotateZ'):
            i += 1; args['rotateZ'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-s', '--scale'):
            i += 1; args['scale'] = float(argv[i]) if i < len(argv) else 1.0
        elif a in ('-tx', '--translateX'):
            i += 1; args['translateX'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-ty', '--translateY'):
            i += 1; args['translateY'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-tz', '--translateZ'):
            i += 1; args['translateZ'] = float(argv[i]) if i < len(argv) else 0
        elif a in ('-sh', '--shDegree'):
            i += 1; args['shDegree'] = int(argv[i]) if i < len(argv) else 0
        elif a in ('-a', '--alpha'):
            i += 1; args['alpha'] = int(argv[i]) if i < len(argv) else 0
        elif a in ('-to', '--transform-order'):
            i += 1; args['transformOrder'] = argv[i] if i < len(argv) else 'RST'
        elif a in ('-ov', '--output-version'):
            i += 1; args['outputVersion'] = int(argv[i]) if i < len(argv) else 0
        elif a in ('-bf', '--block-format'):
            i += 1; args['blockFormat'] = int(argv[i]) if i < len(argv) else 0
        elif a in ('-q', '--quality'):
            i += 1; args['quality'] = max(1, min(int(argv[i]) if i < len(argv) else 5, 9))
        elif a in ('-cs', '--cut-size'):
            i += 1; args['cutSize'] = int(argv[i]) if i < len(argv) else 102400
        elif a.startswith('-'):
            print(f"Warning: Unknown option {a}")
        i += 1
    return args


def _read_file(path: str):
    if is_net_file(path):
        print(f"[Info] Downloading {path}...")
        path = read_remote_to_local(path)
        print("[Info] Download complete")
    ext = file_ext_name(path).lower()
    hdr: Any = None
    if ext == '.ply':
        hdr, data = ply.read_ply(path)
        return data, hdr.max_sh_degree() if hdr else 0
    elif ext == '.splat':
        return splat.read_splat(path), 0
    elif ext == '.spx':
        hdr, data = spx.read_spx(path)
        return data, hdr.sh_degree
    elif ext == '.spz':
        hdr, data = spz.read_spz(path)
        return data, hdr.sh_degree
    elif ext == '.glb':
        deg, data = glb.read_glb(path)
        return data, deg
    elif ext == '.ksplat':
        hdr, data = ksplat.read_ksplat(path)
        return data, hdr.sh_degree
    elif ext == '.sog' or path.lower().endswith('meta.json'):
        hdr, data = sog.read_sog(path)
        return data, hdr.sh_degree
    else:
        print(f"Error: Unsupported input format: {path}")
        sys.exit(1)


def _write_file(path: str, data, sh_degree: int, args: dict):
    ext = file_ext_name(path).lower()
    if ext == '.ply':
        ply.write_ply(path, data, sh_degree=sh_degree)
    elif ext == '.splat':
        splat.write_splat(path, data)
    elif ext == '.spx':
        ver = args.get('outputVersion', 3)
        bf = args.get('blockFormat', spx.BF_SPLAT220_WEBP)
        q = args.get('quality', 90)
        spx.write_spx(path, data, sh_degree=sh_degree, version=ver, block_format=bf, quality=q)
    elif ext == '.spz':
        ver = args.get('outputVersion', 4)
        spz.write_spz(path, data, sh_degree=sh_degree, version=ver)
    elif ext == '.glb':
        glb.write_glb(path, data, sh_degree=sh_degree)
    elif ext == '.sog' or path.lower().endswith('meta.json'):
        sog.write_sog(path, data, sh_degree=sh_degree, quality=args.get('quality', 5))
    else:
        print(f"Error: Unsupported output format: {path}")
        sys.exit(1)


def process_data(data, args):
    alpha = args.get('alpha', 0)
    if alpha > 0:
        print(f"[Info] Filtering alpha >= {alpha}")
        data = data.filter_alpha(alpha)

    rx, ry, rz = args.get('rotateX', 0), args.get('rotateY', 0), args.get('rotateZ', 0)
    sf = args.get('scale', 1.0)
    tx, ty, tz = args.get('translateX', 0), args.get('translateY', 0), args.get('translateZ', 0)

    if rx or ry or rz:
        print(f"[Info] Rotating: X={rx} Y={ry} Z={rz}")
        transform.rotate(data, rx, ry, rz)
    if sf != 1.0:
        print(f"[Info] Scaling: {sf}")
        transform.scale(data, sf)
    if tx or ty or tz:
        print(f"[Info] Translating: X={tx} Y={ty} Z={tz}")
        transform.translate(data, tx, ty, tz)

    # Morton sort for compressed formats (match Go's ProcessDatas → Sort)
    out_path = args.get('output', '')
    if out_path and not out_path.lower().endswith('.ply') and not out_path.lower().endswith('.splat'):
        morton.sort_morton(data)

    return data


def cmd_convert(args):
    in_path = args.get('input')
    out_path = args.get('output')
    if not in_path or not out_path:
        print("Error: -i and -o required"); sys.exit(1)

    print(f"[Info] {in_path} -> {out_path}")
    t0 = time.time()
    with Progress(callback=default_callback):
        data, sh = _read_file(in_path)
    print(f"[Info] Read {data.count} splats (SH:{sh})")

    # Determine output SH degree
    out_sh = args.get('shDegree', None)
    if out_sh is None:
        out_sh_map = {'spz': sh, 'spx': sh, 'glb': sh, 'sog': sh, 'ply': sh}
        ext = file_ext_name(out_path).lower()[1:]
        out_sh = out_sh_map.get(ext, 0)
    args['shDegree'] = out_sh

    data = process_data(data, args)
    print(f"[Info] Writing {data.count} splats")
    with Progress(callback=default_callback):
        _write_file(out_path, data, out_sh, args)
    print(f"[Info] Done in {time.time() - t0:.2f}s")


def cmd_simplify(args):
    in_path = args.get('input')
    out_path = args.get('output')
    if not in_path or not out_path:
        print("Error: -i and -o required"); sys.exit(1)
    print(f"[Info] Simplify: {in_path} -> {out_path}")
    t0 = time.time()
    with Progress(callback=default_callback):
        data, sh = _read_file(in_path)
    print(f"[Info] Read {data.count} splats")
    result = simp_module.simplify(data)
    print(f"[Info] Simplified: {data.count} -> {result.count}")
    sh = args.get('shDegree', sh)
    _write_file(out_path, result, sh, args)
    print(f"[Info] Done in {time.time() - t0:.2f}s")


def cmd_lod(args):
    in_path = args.get('input')
    out_path = args.get('output') or 'lod-meta.json'
    data, sh = _read_file(in_path)
    cut = args.get('cutSize', 102400)
    print(f"[Info] Building LOD: {data.count} splats, cut_size={cut}")
    t0 = time.time()
    data.lod = data.lod if data.lod.size > 0 else None
    if data.lod is None or data.lod.size == 0 or int(data.lod.max()) == 0:
        data.lod = __import__('numpy').zeros(data.count, dtype=__import__('numpy').uint16)
    root = lod_module.build_btree(data, cut_size=cut)
    tiles, meta = lod_module.build_tiles_from_btree(data, root, lod_levels=1, sh_degree=sh)
    json_str = lod_module.lod_meta_to_json(meta)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json_str)
    print(f"[Info] LOD meta written: {out_path} ({len(tiles.files)} tiles)")
    print(f"[Info] Done in {time.time() - t0:.2f}s")


def cmd_obj(args):
    in_path = args.get('input')
    out_path = args.get('output')
    if not in_path or not out_path:
        print("Error: -i and -o required"); sys.exit(1)
    rx = args.get('rotateX', 0)
    ry = args.get('rotateY', 0)
    rz = args.get('rotateZ', 0)
    sf = args.get('scale', 1.0)
    tx = args.get('translateX', 0)
    ty = args.get('translateY', 0)
    tz = args.get('translateZ', 0)
    order = args.get('transformOrder', 'rst').lower()
    print(f"[Info] Transform OBJ: {in_path} -> {out_path}")
    obj.obj_transform(in_path, out_path, rx, ry, rz, sf, tx, ty, tz, order)
    print("[Info] Done")


def cmd_autocut(args):
    in_path = args.get('input')
    out_path = args.get('output') or 'lod-meta.json'
    if not in_path:
        print("Error: -i required"); sys.exit(1)
    cut_size = args.get('cutSize', 102400)
    sh = args.get('shDegree', 3)
    print(f"[Info] Auto-cut: {in_path} -> {out_path}")
    t0 = __import__('time').time()
    with Progress(callback=default_callback):
        data, _ = _read_file(in_path)
    autocut.autocut(data, out_path, sh_degree=sh, cut_size=cut_size)
    print(f"[Info] Done in {__import__('time').time() - t0:.2f}s")


def cmd_cut(args: dict) -> None:
    inputs = args.get('inputs', [])
    lod_levels = args.get('lodLevels', [])
    if not inputs:
        print("Error: -i required"); return
    if not lod_levels:
        lod_levels = [0] * len(inputs)
    if len(inputs) != len(lod_levels):
        print("Error: -i and -l pair mismatch"); return
    out_path = args.get('output') or 'lod-meta.json'
    cut_size = args.get('cutSize', 102400)
    if cut_size <= 0:
        print("Error: cut-size must be > 0"); return

    import numpy as np
    from pygsbox.advanced import lod as lod_module
    from pygsbox.core.splat_data import SplatData
    from pygsbox.core.morton import sort_morton
    from pygsbox.formats.sog import write_sog

    print(f"[Info] Cut: {len(inputs)} inputs -> {out_path}")
    quality = args.get('quality', 5)
    t0 = time.time()

    max_sh = 0
    merged = SplatData(0)
    for input_path, lod_level in zip(inputs, lod_levels):
        data, sh = _read_file(input_path)
        max_sh = max(max_sh, sh)
        data.lod = np.full(data.count, lod_level, dtype=np.uint16)
        merged.append(data)

    sort_morton(merged)

    lod_levels_count = max(lod_levels) + 1

    sh_centroids = None
    if max_sh > 0:
        from pygsbox.advanced.kmeans import rewrite_sh_by_kmeans
        t0_km = time.time()
        print(f"[Info] Computing global SH palette on {merged.count} points...")
        sh_centroids, _, _ = rewrite_sh_by_kmeans(merged, max_sh, quality=quality)
        print(f"[Info] Global SH palette done in {time.time() - t0_km:.1f}s "
              f"(palette_size={len(sh_centroids) if sh_centroids is not None else 0})")

    root = lod_module.build_btree(merged, cut_size=cut_size, lod_levels=lod_levels_count)
    tiles, meta = lod_module.build_tiles_from_btree(merged, root, lod_levels=lod_levels_count, sh_degree=max_sh)

    out_dir = os.path.dirname(out_path) or '.'
    for splat_file in tiles.files.values():
        if splat_file.datas is None or splat_file.datas.count == 0:
            continue
        sog_path = os.path.join(out_dir, splat_file.url)
        write_sog(sog_path, splat_file.datas, sh_degree=max_sh, as_zip=True, quality=quality,
                  sh_centroids=sh_centroids)
        splat_file.datas = None
        print(f"  wrote {splat_file.url}")

    json_str = lod_module.lod_meta_to_json(meta)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json_str)
    print(f"[Info] LOD meta written: {out_path} ({len(tiles.files)} tiles)")
    print(f"[Info] Done in {time.time() - t0:.2f}s")


def cmd_info(args):
    in_path = args.get('input')
    if not in_path:
        print("Error: -i required"); sys.exit(1)
    print(f"\nFile: {in_path}")
    print(f"Size: {os.path.getsize(in_path) / 1024 / 1024:.2f} MB")

    ext = file_ext_name(in_path).lower()
    hdr: Any = None
    try:
        if ext == '.ply':
            hdr, data = ply.read_ply(in_path)  # type: ignore[assignment]
            t = "Compressed PLY" if hdr.is_compressed_ply() else ("RGB PLY" if hdr.is_rgb_ply() else "3DGS PLY")
            print(f"Format: {t}\nVertex count: {data.count}\nSH degree: {hdr.max_sh_degree()}")
            if hdr.comment:
                print(f"Comment: {hdr.comment}")
        elif ext == '.splat':
            data = splat.read_splat(in_path)
            print(f"Format: Splat\nSplat count: {data.count}")
        elif ext == '.spx':
            hdr, data = spx.read_spx(in_path)
            print(f"Format: SPX v{hdr.version}\nSplat count: {data.count}\nSH degree: {hdr.sh_degree}")
            print(hdr.to_string())
        elif ext == '.spz':
            hdr, data = spz.read_spz(in_path)
            print(f"Format: SPZ v{hdr.version}\nSplat count: {data.count}\nSH degree: {hdr.sh_degree}")
        elif ext == '.glb':
            deg, data = glb.read_glb(in_path)
            print(f"Format: GLB (KHR_gaussian_splatting)\nSplat count: {data.count}\nSH degree: {deg}")
        elif ext == '.sog' or in_path.lower().endswith('meta.json'):
            hdr, data = sog.read_sog(in_path)
            print(f"Format: SOG v{hdr.version}\nSplat count: {data.count}\nSH degree: {hdr.sh_degree}")
        elif ext == '.ksplat':
            hdr, data = ksplat.read_ksplat(in_path)
            print(f"Format: KSplat\nSplat count: {data.count}")
            print(hdr.to_string())
        else:
            print("Unsupported format")
    except Exception as e:
        print(f"Error reading file: {e}")
    print()


def main():
    if len(sys.argv) < 2:
        usage(); return

    args = parse_args(sys.argv)
    cmd = args.get('command', '')

    if cmd == 'help':
        usage()
    elif cmd == 'version':
        print(f"pygsbox {version.VER}")
    elif cmd == 'info':
        cmd_info(args)
    elif cmd == 'simplify':
        cmd_simplify(args)
    elif cmd == 'lod':
        cmd_lod(args)
    elif cmd == 'obj':
        cmd_obj(args)
    elif cmd == 'autocut':
        cmd_autocut(args)
    elif cmd == 'cut':
        cmd_cut(args)
    elif cmd == 'check_update':
        print(check_update())
    elif cmd in ('convert', 'ply2splat', 'splat2ply', 'ply2spz', 'spz2ply',
                 'ply2glb', 'glb2ply', 'spz2glb', 'glb2spz', 'ply2ply'):
        cmd_convert(args)
    else:
        usage()


if __name__ == '__main__':
    main()

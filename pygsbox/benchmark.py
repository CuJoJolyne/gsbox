#!/usr/bin/env python3
"""Performance benchmark for pygsbox format readers/writers."""
import sys, os, time, tempfile, gc, json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pygsbox.core.splat_data import SplatData
from pygsbox.formats import ply, splat, spz, spx, sog, glb
from pygsbox.core import morton

def gen_data(n: int) -> SplatData:
    rng = np.random.default_rng(42)
    data = SplatData(n)
    data.position = rng.normal(0, 3, (n, 3)).astype(np.float32)
    data.scale = rng.normal(-2.5, 0.8, (n, 3)).astype(np.float32)
    data.color = rng.integers(30, 225, (n, 4), dtype=np.uint8)
    data.rotation = rng.integers(40, 220, (n, 4), dtype=np.uint8)
    data.sh = rng.integers(0, 256, (n, 45), dtype=np.uint8)
    return data


def bench(name, fn_read, fn_write, data, sh_degree=0, **write_kw):
    tmp = os.path.join(tempfile.mkdtemp(), f'bench_{name}')
    ext = name.split('/')[0]
    tmpfile = f'{tmp}.{ext}' if ext not in ['sog', 'meta'] else tmp + '.sog'

    gc.collect()
    t0 = time.perf_counter()
    fn_write(tmpfile, data, **write_kw) if write_kw else fn_write(tmpfile, data)
    tw = time.perf_counter() - t0

    file_size = os.path.getsize(tmpfile)

    gc.collect()
    t0 = time.perf_counter()
    fn_read(tmpfile) if not write_kw else None  # just calling the right read
    if name.startswith('ply'):
        _, result = ply.read_ply(tmpfile)
    elif name.startswith('splat'):
        result = splat.read_splat(tmpfile)
    elif name.startswith('spz'):
        _, result = spz.read_spz(tmpfile)
    elif name.startswith('spx'):
        _, result = spx.read_spx(tmpfile)
    elif name.startswith('sog'):
        _, result = sog.read_sog(tmpfile)
    elif name.startswith('glb'):
        _, result = glb.read_glb(tmpfile)
    else:
        result = SplatData(0)
    tr = time.perf_counter() - t0

    pos_err = np.max(np.abs(data.position - result.position))
    ratio = file_size / (data.count * 248) * 100  # vs uncompressed PLY (~248 bytes/splat)

    os.unlink(tmpfile)
    return tw, tr, file_size, ratio, pos_err


def main():
    sizes = [5_000, 50_000, 200_000]
    results = []

    for n in sizes:
        print(f'\n{"="*60}')
        print(f'  {n:,} points')
        print(f'{"="*60}')
        data = gen_data(n)
        entries = []

        # PLY
        try:
            tw, tr, sz, ratio, err = bench('ply', ply.read_ply, ply.write_ply, data)
            entries.append(('PLY', tw, tr, sz, err))
            print(f'  PLY     write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  PLY     ERROR: {e}')

        # SPZ v3
        try:
            tw, tr, sz, ratio, err = bench('spz', spz.read_spz, spz.write_spz, data, version=3)
            entries.append(('SPZ v3', tw, tr, sz, err))
            print(f'  SPZ v3  write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  SPZ v3  ERROR: {e}')

        # SPZ v4
        try:
            tw, tr, sz, ratio, err = bench('spz', spz.read_spz, spz.write_spz, data, version=4)
            entries.append(('SPZ v4', tw, tr, sz, err))
            print(f'  SPZ v4  write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  SPZ v4  ERROR: {e}')

        # SPX v3
        try:
            tw, tr, sz, ratio, err = bench('spx', spx.read_spx, lambda p,d,**kw: spx.write_spx(p,d,version=3), data)
            entries.append(('SPX v3', tw, tr, sz, err))
            print(f'  SPX v3  write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  SPX v3  ERROR: {e}')

        # SOG (needs Pillow)
        try:
            from PIL import Image
            tw, tr, sz, ratio, err = bench('sog', sog.read_sog, sog.write_sog, data, as_zip=False)
            entries.append(('SOG v2', tw, tr, sz, err))
            print(f'  SOG v2  write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  SOG v2  SKIP (Pillow not available)')

        # Splat
        try:
            tw, tr, sz, ratio, err = bench('splat', splat.read_splat, splat.write_splat, data)
            entries.append(('Splat', tw, tr, sz, err))
            print(f'  Splat   write={tw:.2f}s read={tr:.2f}s size={sz//1024}KB comp={ratio:.1f}% err={err:.4f}')
        except Exception as e:
            print(f'  Splat   ERROR: {e}')

        # Throughput summary
        print(f'\n  {"Format":<8} {"Write (pts/s)":>16} {"Read (pts/s)":>16}')
        for name, tw, tr, _, _ in entries:
            wps = n / tw if tw > 0 else 0
            rps = n / tr if tr > 0 else 0
            print(f'  {name:<8} {wps:>15,.0f} {rps:>15,.0f}')

    print(f'\nDone. All benchmarks complete.')


if __name__ == '__main__':
    main()

import os
import sys
import tempfile
import struct
import numpy as np

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(parent_dir))

from pygsbox.core.splat_data import SplatData, from_splat_format_bytes, to_splat_format_bytes
from pygsbox.common.codec import (
    encode_splat_opacity, decode_splat_opacity,
    encode_splat_color, decode_splat_color,
    encode_splat_scale, decode_splat_scale,
    encode_splat_rotation, decode_splat_rotation,
    spz_encode_scale, spz_decode_scale,
    spz_encode_rotations_v3v4, spz_decode_rotations_v3v4,
    sog_encode_rotations, sog_decode_rotations,
)
from pygsbox.core.morton import V3MinMax, compute_xyz_min_max, sort_morton, encode_morton3


def test_splat_data_creation():
    """Test SplatData creation and basic operations."""
    print("Test: SplatData creation...", end=" ")
    data = SplatData(100)
    assert data.count == 100
    assert data.position.shape == (100, 3)
    assert data.scale.shape == (100, 3)
    assert data.color.shape == (100, 4)
    assert data.rotation.shape == (100, 4)
    assert data.sh.shape == (100, 45)
    print("PASS")


def test_splat_data_append():
    """Test SplatData append operation."""
    print("Test: SplatData append...", end=" ")
    d1 = SplatData(50)
    d1.position[:, 0] = 1.0
    d2 = SplatData(30)
    d2.position[:, 0] = 2.0

    d1.append(d2)
    assert d1.count == 80
    assert np.sum(d1.position[:, 0] == 1.0) == 50
    assert np.sum(d1.position[:, 0] == 2.0) == 30
    print("PASS")


def test_splat_data_filter_alpha():
    """Test alpha filtering."""
    print("Test: Alpha filtering...", end=" ")
    data = SplatData(100)
    data.color[:, 3] = np.random.randint(0, 256, 100, dtype=np.uint8)

    filtered = data.filter_alpha(128)
    assert filtered.count == np.sum(data.color[:, 3] >= 128)
    print("PASS")


def test_splat_data_bounds():
    """Test bounding box computation."""
    print("Test: Bounds computation...", end=" ")
    data = SplatData(10)
    data.position[:, 0] = np.linspace(-5, 5, 10)
    data.position[:, 1] = np.linspace(-3, 3, 10)
    data.position[:, 2] = np.linspace(-2, 2, 10)

    min_pos, max_pos = data.compute_bounds()
    assert min_pos[0] == -5.0
    assert max_pos[0] == 5.0
    print("PASS")


def test_opacity_codec():
    """Test opacity roundtrip: logit val -> uint8 -> logit val."""
    print("Test: Opacity codec...", end=" ")
    test_vals = [-2.0, 0.0, 1.0, 5.0]
    for v in test_vals:
        encoded = encode_splat_opacity(v)
        decoded = decode_splat_opacity(encoded)
        assert abs(decoded - v) < 0.6, f"opacity codec failed for {v}: encoded={encoded} got {decoded:.3f}"
    print("PASS")


def test_color_codec():
    """Test color encoding/decoding."""
    print("Test: Color codec...", end=" ")
    test_vals = [0.0, 0.5, 1.0, -0.5]
    for v in test_vals:
        encoded = encode_splat_color(v)
        decoded = decode_splat_color(encoded)
        assert abs(decoded - v) < 0.01, f"color codec failed for {v}: got {decoded}"
    print("PASS")


def test_scale_codec():
    """Test scale encoding/decoding."""
    print("Test: Scale codec...", end=" ")
    test_vals = [0.1, 1.0, 2.5]
    for v in test_vals:
        encoded = encode_splat_scale(v)
        decoded = decode_splat_scale(encoded)
        assert abs(decoded - v) < 0.001, f"scale codec failed for {v}: got {decoded}"
    print("PASS")


def test_rotation_codec():
    """Test rotation encoding/decoding."""
    print("Test: Rotation codec...", end=" ")
    test_vals = [0.0, 0.5, -0.5, 0.9]
    for v in test_vals:
        encoded = encode_splat_rotation(v)
        decoded = decode_splat_rotation(encoded)
        assert abs(decoded - v) < 0.01, f"rotation codec failed for {v}: got {decoded}"
    print("PASS")


def test_spz_scale_codec():
    """Test SPZ scale encoding/decoding."""
    print("Test: SPZ scale codec...", end=" ")
    test_vals = [-5.0, 0.0, 2.0]
    for v in test_vals:
        encoded = spz_encode_scale(v)
        decoded = spz_decode_scale(encoded)
        assert abs(decoded - v) < 0.1, f"spz scale codec failed for {v}: got {decoded}"
    print("PASS")


def test_spz_rotation_v3v4_codec():
    """Test SPZ v3/v4 rotation encoding/decoding."""
    print("Test: SPZ rotation v3v4 codec...", end=" ")
    rw, rx, ry, rz = 200, 100, 80, 150
    encoded = spz_encode_rotations_v3v4(rw, rx, ry, rz)
    assert len(encoded) == 4
    drw, drx, dry, drz = spz_decode_rotations_v3v4(encoded)
    assert 0 <= drw <= 255
    assert 0 <= drx <= 255
    assert 0 <= dry <= 255
    assert 0 <= drz <= 255
    print("PASS")


def test_sog_rotation_codec():
    """Test SOG rotation roundtrip: uint8 quat -> RGBA -> uint8 quat."""
    print("Test: SOG rotation codec...", end=" ")
    rw, rx, ry, rz = 128, 200, 60, 180
    r, g, b, a = sog_encode_rotations(rw, rx, ry, rz)
    drw, drx, dry, drz = sog_decode_rotations(r, g, b, a)
    assert abs(drw - rw) < 30, f"rw: {drw} vs {rw}"
    assert abs(drx - rx) < 30, f"rx: {drx} vs {rx}"
    assert abs(dry - ry) < 30, f"ry: {dry} vs {ry}"
    assert abs(drz - rz) < 30, f"rz: {drz} vs {rz}"
    print("PASS")


def test_morton_encoding():
    """Test Morton code encoding."""
    print("Test: Morton encoding...", end=" ")
    positions = np.array([[0.5, 0.5, 0.5], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]], dtype=np.float32)
    from pygsbox.core.morton import V3MinMax
    mm = V3MinMax()
    mm.min_x, mm.min_y, mm.min_z = 0.0, 0.0, 0.0
    mm.max_x, mm.max_y, mm.max_z = 1.0, 1.0, 1.0
    mm.len_x, mm.len_y, mm.len_z = 1.0, 1.0, 1.0

    codes = encode_morton3(positions, mm)
    assert len(codes) == 3
    assert codes[2] == 0
    print("PASS")


def test_morton_sort():
    """Test Morton code sorting."""
    print("Test: Morton sort...", end=" ")
    data = SplatData(20)
    data.position = np.random.randn(20, 3).astype(np.float32)

    original_positions = data.position.copy()
    sort_morton(data)

    assert data.count == 20
    assert not np.array_equal(data.position, original_positions)
    print("PASS")


def test_splat_roundtrip():
    """Test splat format bytes roundtrip."""
    print("Test: Splat roundtrip...", end=" ")
    data = SplatData(10)
    data.position = np.random.randn(10, 3).astype(np.float32)
    data.scale = np.random.randn(10, 3).astype(np.float32)
    data.color = np.random.randint(0, 256, (10, 4), dtype=np.uint8)
    data.rotation = np.random.randint(0, 256, (10, 4), dtype=np.uint8)

    encoded = to_splat_format_bytes(data)
    assert len(encoded) == 10 * 32

    decoded = from_splat_format_bytes(encoded, 10)
    assert np.allclose(decoded.position, data.position)
    assert np.allclose(decoded.scale, data.scale)
    assert np.array_equal(decoded.color, data.color)
    assert np.array_equal(decoded.rotation, data.rotation)
    print("PASS")


def test_spz_v3_roundtrip():
    """Test SPZ v3 write/read roundtrip."""
    print("Test: SPZ v3 roundtrip...", end=" ")
    from pygsbox.formats.spz import write_spz, read_spz
    np.random.seed(42)
    N = 30
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 2.0
    data.scale = np.random.randn(N, 3).astype(np.float32) * 0.5 - 3.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    data.sh = np.random.randint(0, 256, (N, 45), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.spz', delete=False) as f:
        path = f.name
    try:
        write_spz(path, data, sh_degree=2, version=3)
        header, decoded = read_spz(path)
        assert decoded.count == N
        assert header.version == 3
        assert header.sh_degree == 2
        assert np.max(np.abs(data.position - decoded.position)) < 0.01
        assert np.max(np.abs(data.scale - decoded.scale)) < 0.1
    finally:
        os.unlink(path)
    print("PASS")


def test_spz_v4_roundtrip():
    """Test SPZ v4 write/read roundtrip."""
    print("Test: SPZ v4 roundtrip...", end=" ")
    from pygsbox.formats.spz import write_spz, read_spz
    try:
        import zstandard
    except ImportError:
        print("SKIP (zstandard not installed)")
        return
    np.random.seed(42)
    N = 30
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 2.0
    data.scale = np.random.randn(N, 3).astype(np.float32) * 0.5 - 3.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    data.sh = np.random.randint(0, 256, (N, 45), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.spz', delete=False) as f:
        path = f.name
    try:
        write_spz(path, data, sh_degree=1, version=4)
        header, decoded = read_spz(path)
        assert decoded.count == N
        assert header.version == 4
        assert header.sh_degree == 1
        assert np.max(np.abs(data.position - decoded.position)) < 0.01
    finally:
        os.unlink(path)
    print("PASS")


def test_glb_roundtrip():
    """Test GLB write/read roundtrip."""
    print("Test: GLB roundtrip...", end=" ")
    from pygsbox.formats.glb import write_glb, read_glb
    np.random.seed(42)
    N = 30
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 2.0
    data.scale = np.random.randn(N, 3).astype(np.float32) * 0.5 - 3.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    data.sh = np.random.randint(0, 256, (N, 45), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.glb', delete=False) as f:
        path = f.name
    try:
        write_glb(path, data, sh_degree=1, glb_extension="KHR_gaussian_splatting")
        sh_deg, decoded = read_glb(path)
        assert decoded.count == N
        assert sh_deg == 1
        assert np.max(np.abs(data.position - decoded.position)) < 0.01
    finally:
        os.unlink(path)
    print("PASS")


def test_glb_sh3_roundtrip():
    """Test GLB write/read roundtrip with SH degree 3."""
    print("Test: GLB SH3 roundtrip...", end=" ")
    from pygsbox.formats.glb import write_glb, read_glb
    np.random.seed(42)
    N = 20
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32)
    data.scale = np.random.randn(N, 3).astype(np.float32) - 2.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.glb', delete=False) as f:
        path = f.name
    try:
        write_glb(path, data, sh_degree=3, glb_extension="KHR_gaussian_splatting")
        sh_deg, decoded = read_glb(path)
        assert decoded.count == N
        assert sh_deg == 3
    finally:
        os.unlink(path)
    print("PASS")


def test_sog_roundtrip():
    """Test SOG write/read roundtrip."""
    print("Test: SOG roundtrip...", end=" ")
    try:
        from PIL import Image
        from pygsbox.formats.sog import write_sog, read_sog
    except ImportError:
        print("SKIP (Pillow not installed)")
        return
    np.random.seed(42)
    N = 30
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 2.0
    data.scale = np.random.randn(N, 3).astype(np.float32) * 0.5 - 3.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "meta.json")
    try:
        write_sog(path, data, sh_degree=0, as_zip=False)
        header, decoded = read_sog(path)
        assert decoded.count == N
        assert np.max(np.abs(data.position - decoded.position)) < 0.01
        assert np.max(np.abs(data.scale - decoded.scale)) < 0.1
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("PASS")


def test_kmeans_fast_path():
    """Test K-Means SH clustering with unique SH values."""
    print("Test: K-Means fast path...", end=" ")
    from pygsbox.advanced import kmeans
    np.random.seed(42)
    N = 50
    data = SplatData(N)
    data.sh = np.random.randint(0, 256, (N, 45), dtype=np.uint8)
    centroids, labels, ps = kmeans.kmeans_sh(data, sh_degree=1, iterations=2)
    assert centroids.shape == (ps, 45)
    assert labels.shape == (N,)
    assert np.all(labels >= 0) and np.all(labels < ps)
    print("PASS")


def test_kmeans_with_duplicates():
    """Test K-Means with duplicate SH values."""
    print("Test: K-Means duplicates...", end=" ")
    from pygsbox.advanced import kmeans
    N = 30
    data = SplatData(N)
    data.sh = np.zeros((N, 45), dtype=np.uint8)
    data.sh[:10, :9] = 100
    data.sh[10:20, :9] = 200
    data.sh[20:30, :9] = 50
    centroids, labels, ps = kmeans.kmeans_sh(data, sh_degree=1, iterations=2)
    assert ps <= N
    assert ps == 3
    print("PASS")


def test_rewrite_sh_by_kmeans():
    """Test rewrite_sh_by_kmeans."""
    print("Test: Rewrite SH by K-Means...", end=" ")
    from pygsbox.advanced import kmeans
    np.random.seed(42)
    N = 40
    data = SplatData(N)
    data.sh = np.random.randint(0, 256, (N, 45), dtype=np.uint8)
    centroids, labels, ps = kmeans.rewrite_sh_by_kmeans(data, sh_degree=1, iterations=2)
    assert ps > 0
    assert centroids is not None
    assert np.array_equal(data.sh, centroids[labels])
    print("PASS")


def test_simplify_basic():
    """Test basic simplification."""
    print("Test: Simplify basic...", end=" ")
    from pygsbox.advanced import simplify
    np.random.seed(42)
    N = 20
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 0.5
    data.scale = np.random.randn(N, 3).astype(np.float32) * 0.1 - 2.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.color[:, 3] = 128
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    result = simplify.simplify(data)
    assert result.count > 0
    assert result.count <= N
    print("PASS")


def test_simplify_low_alpha_filter():
    """Test simplification filters out low alpha."""
    print("Test: Simplify alpha filter...", end=" ")
    from pygsbox.advanced import simplify
    N = 30
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32)
    data.scale = np.random.randn(N, 3).astype(np.float32) - 2.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.color[:, 3] = 10
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    result = simplify.simplify(data)
    assert result.count == 0
    print("PASS")


def test_btree_build():
    """Test B-Tree build with multiple levels."""
    print("Test: B-Tree build...", end=" ")
    from pygsbox.advanced import lod
    np.random.seed(42)
    N = 300
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 10.0
    data.scale = np.random.randn(N, 3).astype(np.float32) - 2.0
    data.color = np.random.randint(30, 225, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(40, 220, (N, 4), dtype=np.uint8)
    data.lod = np.random.randint(0, 2, N, dtype=np.uint16)
    root = lod.build_btree(data, cut_size=50, lod_levels=2)
    assert root.is_leaf == False
    assert len(root.children) == 2
    print("PASS")


def test_lod_tiles_and_meta():
    """Test SplatTiles + LodMeta generation."""
    print("Test: LOD tiles + meta...", end=" ")
    from pygsbox.advanced import lod
    np.random.seed(42)
    N = 200
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 5.0
    data.scale = np.random.randn(N, 3).astype(np.float32) - 2.0
    data.lod = np.random.randint(0, 2, N, dtype=np.uint16)
    root = lod.build_btree(data, cut_size=100, lod_levels=2)
    tiles, lod_meta = lod.build_tiles_from_btree(data, root, lod_levels=2, sh_degree=1)
    assert len(tiles.files) > 0
    assert len(lod_meta.filenames) == len(tiles.files)
    print("PASS")


def test_lod_meta_json_roundtrip():
    """Test LodMeta JSON roundtrip."""
    print("Test: LodMeta JSON roundtrip...", end=" ")
    from pygsbox.advanced import lod
    np.random.seed(42)
    N = 100
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 5.0
    data.scale = np.random.randn(N, 3).astype(np.float32) - 2.0
    data.lod = np.zeros(N, dtype=np.uint16)
    root = lod.build_btree(data, cut_size=200, lod_levels=1)
    tiles, lod_meta = lod.build_tiles_from_btree(data, root, lod_levels=1)
    json_str = lod.lod_meta_to_json(lod_meta)
    meta2 = lod.lod_meta_from_json(json_str)
    assert meta2.lod_levels == lod_meta.lod_levels
    assert meta2.filenames == lod_meta.filenames
    print("PASS")


def test_btree_single_tile():
    """Test B-Tree with data smaller than cut size."""
    print("Test: B-Tree single tile...", end=" ")
    from pygsbox.advanced import lod
    data = SplatData(30)
    data.position = np.random.randn(30, 3).astype(np.float32)
    data.lod = np.zeros(30, dtype=np.uint16)
    root = lod.build_btree(data, cut_size=1000, lod_levels=1)
    assert root.is_leaf == True
    print("PASS")


def test_compress_gzip_roundtrip():
    """Test gzip compress/decompress roundtrip."""
    print("Test: Gzip roundtrip...", end=" ")
    from pygsbox.common.compress import compress_gzip, decompress_gzip
    original = b"hello world " * 100
    assert decompress_gzip(compress_gzip(original)) == original
    print("PASS")


def test_compress_webp_dimensions():
    """Test WebP dimension calculation."""
    print("Test: WebP dimensions...", end=" ")
    from pygsbox.common.compress import compute_width_height
    w, h = compute_width_height(200)
    assert w * h * 4 >= 200
    print("PASS")


def test_file_utils_path():
    """Test file extension and URL detection."""
    print("Test: File utils path...", end=" ")
    from pygsbox.common.file_utils import file_ext_name, is_net_file
    assert file_ext_name("/a/b/c.ply") == ".ply"
    assert is_net_file("https://example.com/model.spz")
    assert not is_net_file("./local.ply")
    print("PASS")


def test_transform_quaternion():
    """Test quaternion rotation of a vector."""
    print("Test: Quaternion rotation...", end=" ")
    from pygsbox.core.transform import Quaternion, Vector3
    q = Quaternion.from_axis_angle((0, 0, 1), 1.5708)
    v = Vector3(1, 0, 0)
    rotated = v.apply_quaternion(q)
    assert abs(rotated.x) < 0.001 and abs(rotated.y - 1.0) < 0.001
    print("PASS")


def test_spx_v3_roundtrip():
    """Test SPX v3 write/read roundtrip."""
    print("Test: SPX v3 roundtrip...", end=" ")
    from pygsbox.formats.spx import read_spx, write_spx, BF_SPLAT220_WEBP
    import tempfile
    np.random.seed(42)
    N = 100
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 5.0
    data.scale = np.full((N, 3), -4.0, dtype=np.float32)
    data.color = np.random.randint(0, 256, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(0, 256, (N, 4), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.spx', delete=False) as f:
        path = f.name
    try:
        write_spx(path, data, version=3, block_format=BF_SPLAT220_WEBP, quality=90)
        hdr, decoded = read_spx(path)
        assert hdr.version == 3
        assert decoded.count == N
        assert np.max(np.abs(data.position - decoded.position)) < 0.05
    finally:
        os.unlink(path)
    print("PASS")


def test_compressed_ply_roundtrip():
    """Test compressed PLY write/read roundtrip."""
    print("Test: Compressed PLY roundtrip...", end=" ")
    from pygsbox.formats.ply import read_ply, write_compressed_ply
    import tempfile
    np.random.seed(42)
    N = 100
    data = SplatData(N)
    data.position = np.random.randn(N, 3).astype(np.float32) * 5.0
    data.scale = np.full((N, 3), -4.0, dtype=np.float32)
    data.color = np.random.randint(0, 256, (N, 4), dtype=np.uint8)
    data.rotation = np.random.randint(0, 256, (N, 4), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as f:
        path = f.name
    try:
        write_compressed_ply(path, data)
        hdr, decoded = read_ply(path)
        assert hdr.is_compressed_ply()
        assert decoded.count == N
    finally:
        os.unlink(path)
    print("PASS")


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("Running pygsbox tests")
    print("=" * 50 + "\n")

    tests = [
        test_splat_data_creation,
        test_splat_data_append,
        test_splat_data_filter_alpha,
        test_splat_data_bounds,
        test_opacity_codec,
        test_color_codec,
        test_scale_codec,
        test_rotation_codec,
        test_spz_scale_codec,
        test_spz_rotation_v3v4_codec,
        test_sog_rotation_codec,
        test_morton_encoding,
        test_morton_sort,
        test_splat_roundtrip,
        test_spz_v3_roundtrip,
        test_spz_v4_roundtrip,
        test_glb_roundtrip,
        test_glb_sh3_roundtrip,
        test_sog_roundtrip,
        test_kmeans_fast_path,
        test_kmeans_with_duplicates,
        test_rewrite_sh_by_kmeans,
        test_simplify_basic,
        test_simplify_low_alpha_filter,
        test_btree_build,
        test_lod_tiles_and_meta,
        test_lod_meta_json_roundtrip,
        test_btree_single_tile,
        test_compress_gzip_roundtrip,
        test_compress_webp_dimensions,
        test_file_utils_path,
        test_transform_quaternion,
        test_spx_v3_roundtrip,
        test_compressed_ply_roundtrip,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50 + "\n")

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

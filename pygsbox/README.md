# pygsbox

Python implementation of [gsbox](https://github.com/gotoeasy/gsbox) - A cross-platform command-line tool for 3D Gaussian Splatting format conversion and optimization.

## Status

🚧 **Active Development** - Phase 1-3 complete, Phase 4 pending

Current version: `v4.8.4` (matching Go implementation)

## Features (Implemented)

✅ **Phase 1: Common Utilities**
- Numerical encoding/decoding functions (SPZ, SPX, SOG, Splat codecs)
- Compression utilities (gzip, xz, zstd, WebP, ZIP)
- File operations

✅ **Phase 2: Core Data Structures**
- `SplatData` - NumPy-based columnar storage for Gaussian splat data
- Geometric transformations (rotation, scale, translation)
- Morton code spatial sorting
- Spherical harmonics rotation

🔄 **Phase 3: Format Readers/Writers** (Complete)
- ✅ PLY format (read/write)
- ✅ Splat format (read/write)
- ✅ SPX format (v3 read/write; v1/v2 in progress)
- ✅ SPZ format (v2/v3/v4 read/write)
- ✅ SOG format (v1/v2 read, v2 write)
- ✅ KSplat format (read only)
- ✅ GLB format (read/write; KHR_gaussian_splatting + SPZ compression + RGB PLY)

## Installation

```bash
cd pygsbox
pip install -r requirements.txt
```

### Single-file executable

Build a standalone `pygsbox.exe` (no Python required):

```bash
pip install pyinstaller
# Option A: use the build script
build.bat

# Option B: manual command
pyinstaller --onefile --name pygsbox pygsbox/cli.py

# Option C: use spec file
pyinstaller pygsbox.spec
```

Output: `dist/pygsbox.exe` (or `dist/pygsbox` on Linux/macOS).

### Dependencies

```
numpy>=1.24
scipy>=1.10
Pillow>=10.0          # WebP support
zstandard>=0.21       # Zstd compression
requests>=2.28        # HTTP download
click>=8.0            # CLI framework (future)
plyfile>=1.0          # PLY utilities (optional)
scikit-learn>=1.3     # K-Means clustering (future)
```

## Usage

### Command Line

```bash
python cli.py [command] [options]
```

#### Convert PLY to Splat

```bash
python cli.py ply2splat -i input.ply -o output.splat
```

#### Convert Splat to PLY

```bash
python cli.py splat2ply -i input.splat -o output.ply -sh 0
```

#### File Information

```bash
python cli.py info -i input.ply
```

#### With Transformations

```bash
python cli.py ply2ply \
  -i input.ply \
  -o output.ply \
  -rx 90 \
  -s 0.5 \
  -tx 1.0
```

### Python API

```python
from pygsbox.formats import ply, splat, spz, sog, ksplat, glb
from pygsbox.core import transform, morton

# Read PLY
header, data = ply.read_ply("input.ply")
print(f"Loaded {data.count} splats")

# Apply transformations
transform.rotate(data, 90, 0, 0)  # Rotate 90° around X
transform.scale(data, 0.5)         # Scale by 0.5
transform.translate(data, 1.0, 0, 0)  # Translate

# Sort for better compression
morton.sort_morton(data)

# SPZ format (v4 with zstd, or v3 with gzip)
spz.write_spz("output.spz", data, sh_degree=1, version=4)
header, data = spz.read_spz("input.spz")

# SOG format (multi-file WebP + JSON)
sog.write_sog("output.sog", data, sh_degree=0)
header, data = sog.read_sog("input.sog")

# KSplat format (read only)
header, data = ksplat.read_ksplat("input.ksplat")

# GLB format (KHR_gaussian_splatting extension)
glb.write_glb("output.glb", data, sh_degree=1)
sh_degree, data = glb.read_glb("input.glb")
```

## Testing

```bash
python tests/test_basic.py
```

## Architecture

### Core Design Patterns

1. **Star Topology Conversion**: All formats convert to/from a unified `SplatData` representation
2. **NumPy Vectorization**: All operations use NumPy arrays for performance
3. **Columnar Storage**: `SplatData` uses separate arrays for each attribute (position, scale, color, rotation, SH)

### Data Structure

```python
class SplatData:
    count: int
    position: np.ndarray  # (N, 3) float32
    scale: np.ndarray     # (N, 3) float32
    color: np.ndarray     # (N, 4) uint8 (RGBA)
    rotation: np.ndarray  # (N, 4) uint8 (quaternion)
    sh: np.ndarray        # (N, 45) uint8 (spherical harmonics)
```

## Development Progress

See `PROGRESS.json` for current development state.

### Next Steps

- [x] Complete SPZ format reader/writer
- [x] Complete SOG format reader/writer
- [x] Add KSplat format reader
- [x] Add GLB format reader/writer
- [ ] Complete SPX format v1/v2 reader/writer
- [ ] Add compressed PLY and RGB PLY readers
- [ ] Add SOG v2 SH centroid/labels write support
- [ ] Implement K-Means clustering for SH compression
- [ ] Implement model simplification (voxelization)
- [ ] Implement LOD system with B-Tree spatial partitioning
- [ ] Add comprehensive CLI with all conversion commands
- [ ] Performance optimization and profiling

## Performance Notes

The Python implementation uses NumPy for all array operations, which provides:
- ✅ Good performance for large datasets (millions of splats)
- ✅ Memory-efficient columnar storage
- ⚠️ Some operations (e.g., rotation) still use loops - to be vectorized

## License

Same as the original [gsbox](https://github.com/gotoeasy/gsbox) project.

## References

- [gsbox](https://github.com/gotoeasy/gsbox) - Original Go implementation
- [3D Gaussian Splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/) - Official 3DGS repository
- [SPX Format Specification](https://github.com/reall3d-com/Reall3dViewer/blob/main/SPX_EN.md)

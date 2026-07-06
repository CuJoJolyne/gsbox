# pygsbox Agent Guide

## Project Overview

pygsbox is a Python port of [gsbox](https://github.com/gotoeasy/gsbox), a cross-platform CLI tool for 3D Gaussian Splatting format conversion.  
Supports 7 formats: `.ply` `.splat` `.spx` `.spz` `.sog` `.ksplat` `.glb`.

## How We Work: Specification-Driven Development

This project follows **Specification-Driven Development (SDD)**:

1. **Spec is primary** — `specs/<module>.spec.md` is the source of truth
2. **Code is generated** — implementation in `<module>.py` is derived from the spec
3. **Spec → Code → Test** — they form a closed loop

### Workflow

```
┌─────────────────────────────────────────────────────┐
│ 1. Read spec: specs/<module>.spec.md                │
│ 2. Understand: Purpose → Data → API → Edge Cases    │
│ 3. Generate: <module>.py from Examples + Algorithm  │
│ 4. Test: python tests/test_basic.py                 │
│ 5. Type-check: python -m mypy pygsbox               │
│ 6. Commit: concise commit message in repo style     │
└─────────────────────────────────────────────────────┘
```

When a bug is found:
→ Fix the **spec** first (update Algorithm or Edge Cases)
→ Regenerate the code
→ Verify the test still passes

## Directory Layout

```
pygsbox/
├── specs/                         # All module specifications
│   ├── _template.spec.md          # Use this to create new specs
│   ├── common/                    # ← mirrors source tree
│   │   ├── codec.spec.md
│   │   ├── compress.spec.md
│   │   ├── file_utils.spec.md
│   │   ├── progress.spec.md
│   │   └── freq.spec.md
│   ├── core/
│   │   ├── splat_data.spec.md
│   │   ├── transform.spec.md
│   │   ├── morton.spec.md
│   │   └── sh_rotation.spec.md
│   ├── formats/
│   │   ├── ply.spec.md
│   │   ├── splat.spec.md
│   │   ├── spx.spec.md
│   │   ├── spz.spec.md
│   │   ├── sog.spec.md
│   │   ├── ksplat.spec.md
│   │   ├── glb.spec.md
│   │   └── obj.spec.md
│   └── advanced/
│       ├── kmeans.spec.md
│       ├── simplify.spec.md
│       ├── lod.spec.md
│       └── autocut.spec.md
├── common/                        # Source code
│   └── codec.py                   # Implemented from specs/common/codec.spec.md
├── AGENTS.md                      # ← This file
└── PROGRESS.json                  # Tracks spec→code mapping status
```

## Code Conventions

### Data Structure
- **SplatData** is the universal interchange format — all readers output it, all writers take it
- Columnar NumPy layout: `position (N,3)`, `scale (N,3)`, `color (N,4)`, `rotation (N,4)`, `sh (N,45)`
- All arrays are float32 for position/scale, uint8 for color/rotation/sh

### Performance
- **Vectorize with NumPy** — never write `for i in range(count)` to decode points
- Use `np.frombuffer(data, dtype=...)` for bulk parsing
- Use `np.clip()` instead of Python `min/max` in loops
- Exception: SPZ per-point decode loop (format requires sequential reading)

### Imports
```python
# Standard: use relative imports within pygsbox
from ..common import codec, compress
from ..core.splat_data import SplatData

# For top-level scripts:
import sys; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pygsbox.formats import spz
```

### Error Handling
- `raise ValueError("description")` for invalid format data
- `raise ImportError("pip install xxx")` for missing optional deps
- Never `sys.exit(1)` in library code — that's for CLI only

### Optional Dependencies
- **Pillow**: WebP support (`.sog`, SPX WebP blocks)
- **zstandard**: zstd compression (SPZ v4)
- **scipy**: cKDTree for K-Means
- Pattern:
```python
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
```

### Type Hints
- All public functions must have type hints
- Use `from typing import Tuple, List, Optional, Dict, Any`
- For numpy arrays use `np.ndarray` (no strict `NDArray[...]` shape constraint)
- Goal: `mypy pygsbox --python-version 3.12` returns `Success: no issues found`

### Testing
- Every spec's **Section 6 (Examples)** should map to a test in `tests/test_basic.py`
- Use `np.random.seed(42)` for deterministic random data
- Tolerance levels:
  - Position: 24-bit fixed → `<0.01`; float32 → `<1e-6`
  - Scale: log encoding → `<0.1`
  - Color: uint8 → `<= 1`
  - Rotation: NQ encoding → 不过分失真即可

### Spec File Naming
- Use lowercase with underscores: `splat_data.spec.md`
- Match the Python module name: `splat_data.spec.md` → `splat_data.py`
- Always start from `_template.spec.md`

## Key Design Decisions

1. **Star topology**: All formats convert to/from SplatData (no N×M converters)
2. **NumPy-first**: Performance depends on avoiding Python loops
3. **Codec separation**: All encoding logic in `common/codec.py`, reusable across formats
4. **Progress callback**: Use `common.progress.Progress` context manager — no hard dependency on any UI lib
5. **CLI auto-detect**: Input/output format determined by file extension, not explicit flags
6. **No HTTP as dep**: Use `urllib.request` from stdlib for remote file download

## When Writing New Specs

1. Copy `specs/_template.spec.md`
2. Fill in all sections — every section is required
3. **Section 2 (Data)** must be precise enough to generate pydantic/dataclass code
4. **Section 3 (API)** must include full signatures with types
5. **Section 6 (Examples)** must be runnable — these become tests
6. **Section 8 (Agent Notes)** must warn about known pitfalls

## Tooling

| Command | Purpose |
|---------|---------|
| `python tests/test_basic.py` | Run all 28 tests |
| `python -m mypy pygsbox --python-version 3.12` | Type check |
| `python pygsbox/benchmark.py` | Performance benchmark |
| `pygsbox --help` | CLI usage |
| `pip install -e .` | Dev install |

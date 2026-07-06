# cli — Command-Line Interface

> Auto-generated code target: `cli.py`

## 1. Purpose

Single entry point for all pygsbox operations. Auto-detects input/output formats by file extension. Supports remote files via HTTP URL.

## 2. Commands

| Command | Function | Shortcuts |
|---------|----------|-----------|
| `convert` | Any format → any format | ply2splat, spz2ply, ... |
| `info` | Display file metadata | — |
| `simplify` | Voxel-based simplification | — |
| `lod` | Build LOD B-Tree tiles | — |
| `obj` | Transform OBJ vertices | — |
| `autocut` | Auto LOD pipeline | — |
| `check_update` | Check for latest version | — |

## 3. Architecture

### 3.1 Format Dispatch

```python
_read_file(path):
    ext = file_ext_name(path).lower()
    readers = {'.ply': ply.read_ply, '.spz': spz.read_spz, ...}
    return readers[ext](path)
```

### 3.2 Argument Parsing

Custom lightweight parser (no click/argparse dependency). Key-value pairs stored in `Dict[str, Any]` because values are mixed types (str, int, float).

### 3.3 HTTP Input

Before dispatch: `if is_net_file(path): path = read_remote_to_local(path)`

## 4. Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| -i, --input | str | — | Input file (local path or HTTP URL) |
| -o, --output | str | — | Output file |
| -sh | int | keep | SH degree (0-3) |
| -a | int | 0 | Alpha filter threshold |
| -rx, -ry, -rz | float | 0 | Rotation (degrees) |
| -s | float | 1.0 | Uniform scale |
| -tx, -ty, -tz | float | 0 | Translation |
| -to | str | RST | Transform order |
| -ov | int | 4/3 | SPZ/SPX output version |
| -bf | int | 220 | SPX block format |
| -q | int | 90 | WebP quality |
| -cs | int | 102400 | B-Tree cut size |

## 5. Examples

```bash
pygsbox convert -i input.ply -o output.spz -sh 1
pygsbox info -i file.spx
pygsbox autocut -i input.ply -o lod-meta.json
pygsbox simplify -i model.ply -o simplified.ply
```

## 6. Dependencies

| Module | Used for |
|--------|----------|
| `pygsbox.formats.*` | All format readers/writers |
| `pygsbox.advanced.*` | simplify, lod, autocut, kmeans |
| `pygsbox.common.file_utils` | is_net_file, read_remote_to_local |
| `pygsbox.common.progress` | Progress, default_callback |

## 7. Agent Notes

- **No external CLI framework**: Custom parser avoids adding click/typer as dependency.
- **Format auto-detect**: Output format determined by file extension (`.spz` → spz.write_spz).
- **HTTP download**: Uses `urllib.request` (stdlib, no requests dep).
- **Progress by default**: Reads are wrapped in `Progress(default_callback)` for large files.

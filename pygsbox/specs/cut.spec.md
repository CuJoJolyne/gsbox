# cut — Multi-input LOD Tile Generation

> Auto-generated code target: `cli.py` (cmd_cut function)

## 1. Purpose

Combine multiple pre-computed LOD model files into a single lod-meta.json.
Each input file has an associated LOD level. Usage matches Go's `cut` command:

```
pygsbox cut -i lod0.ply -l 0 -i lod1.ply -l 1 -i lod2.ply -l 2 -o lod-meta.json
```

## 2. Argument Parsing (parse_args)

Currently `parse_args` does NOT support repeating `-i` / `-l` flags.
Modify the `-i` / `-l` handlers to accumulate values into lists:

```
elif a in ('-i', '--input'):
    i += 1; args.setdefault('inputs', []).append(argv[i])
elif a in ('-l', '--lod-level'):    # ← NEW
    i += 1; args.setdefault('lodLevels', []).append(int(argv[i]))
```

Also add `'cut'` to the command list.

## 3. cmd_cut Function

### 3.1 Signature

`def cmd_cut(args: dict) -> None`

### 3.2 Input

- `args['inputs']`: list of file path strings (one per LOD level)
- `args['lodLevels']`: list of integer LOD levels (same length as inputs)
- `args['output']` or 'lod-meta.json': output JSON file path
- `args.get('cutSize', 102400)`: B-Tree leaf node size

### 3.3 Algorithm

```
1. Initialize merged = SplatData(0)
2. For each (input_path, lod_level) in zip(inputs, lodLevels):
   a. data, _ = _read_file(input_path)
   b. data.lod = numpy.full(data.count, lod_level, dtype=uint16)
   c. merged.append(data)
3. root = lod_module.build_btree(merged, cut_size=cut_size, lod_levels=max(lodLevels)+1)
4. tiles, meta = lod_module.build_tiles_from_btree(merged, root, lod_levels=max(lodLevels)+1)
5. json_str = lod_module.lod_meta_to_json(meta)
6. Write json_str to output path
7. print summary: number of tiles and output path
```

### 3.4 Imports Needed in cmd_cut

```python
from pygsbox.advanced import lod as lod_module
from pygsbox.core.splat_data import SplatData
import numpy as np
import os
```

## 4. Edge Cases

- Empty inputs or uneven lengths: `print("Error: -i and -l pair mismatch")` and return
- lod_levels = []: default to `[0]` for single input
- cut_size must be > 0

## 5. Main dispatch

Add in `main()`:
```python
elif cmd == 'cut':
    cmd_cut(args)
```

Add in `usage()`:
```
print("  cut             Combine multiple LOD models into lod-meta.json")
```

## 6. Examples

### 6.1 Basic cut

```bash
pygsbox cut -i C:/data/lod0.ply -l 0 -i C:/data/lod1.ply -l 1 -o C:/data/lod-meta.json
```

Expected: lod-meta.json with lodLevels=2, filenames list, tree structure

### 6.2 Validation

```python
# After running cut, verify:
import json
meta = json.load(open('lod-meta.json'))
assert meta['lodLevels'] >= 2
assert len(meta['filenames']) > 0
assert 'tree' in meta
```

## 7. Dependencies

| Module | Used for |
|--------|----------|
| pygsbox.advanced.lod | build_btree, build_tiles_from_btree, lod_meta_to_json |
| pygsbox.core.splat_data | SplatData |
| numpy | full() for lod assignment |
| pygsbox.cli._read_file | existing format dispatch |
| os | makedirs for output |

## 8. Agent Notes

- **Modify existing cli.py file** — add to parse_args, add cmd_cut, add to main, update usage
- **Do NOT modify** _read_file, _write_file, process_data, or any other functions
- **Use** `args.setdefault('inputs', []).append(...)` to handle repeated -i flags
- **`_read_file` returns** `(SplatData, sh_degree)` — use the SplatData, ignore sh_degree for cut
- **lod_levels default**: if `-l` was not specified for a given `-i`, use lod_level=0
- **lod_levels parameter**: derived automatically from the maximum LOD level in the inputs

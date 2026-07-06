# progress — Progress Reporting Framework

> Auto-generated code target: `common/progress.py`

## 1. Purpose

Lightweight progress reporting via context manager + callback.  
Zero dependencies — no progress bar library, no ANSI escape codes required.

Readers/writers call `Progress.report(phase, current, total)` internally;  
users wrap operations in `with Progress(callback=fn):` to see output.

## 2. Data Structures

### Phase Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `PHASE_JOIN` | -1 | Merging multiple files |
| `PHASE_READ` | 0 | Reading a format |
| `PHASE_WRITE` | 2 | Writing a format |
| `PHASE_KMEANS` | 3 | K-Means clustering |
| `PHASE_CUT` | 4 | B-Tree spatial splitting |

### Types

```python
ProgressCallback = Callable[[int, int, int], None]
```

## 3. Public API

### `class Progress`

#### `__init__(self, callback: Optional[ProgressCallback] = None, throttle_ms: int = 100)`
- **Description**: Create progress context with optional callback.
- **Default**: No callback → `report()` is a no-op.

#### `__enter__(self) -> Progress`
- **Description**: Push this instance as the active progress context.
- **Side Effects**: Sets `Progress._instance = self`.

#### `__exit__(self, *args) -> None`
- **Description**: Restore previous progress context.

#### `report(phase: int, current: int, total: int)` (classmethod)
- **Description**: If active context has callback, call it (throttled).
- **Throttle**: Skip calls within `throttle_ms` of last report.
- **Error Safety**: Catches and ignores exceptions from callback.

#### `done(phase: int, total: int)` (classmethod)
- **Description**: Report 100% completion for a phase.

### `default_callback(phase: int, current: int, total: int) -> None`
- **Description**: Simple text progress bar writing to stderr.
- **Format**: `\r  [Read  ] [#############---------]  45.2%`
- **Output**: `sys.stderr` (not stdout — keeps data output clean).

## 4. Edge Cases

| Scenario | Behavior |
|----------|----------|
| No Progress context active | `report()` returns immediately |
| callback raises Exception | Caught and ignored |
| total=0 | Division handled (pct=0) |
| Nested Progress contexts | Inner `__exit__` restores outer |
| Thread safety | Not thread-safe (single _instance) |

## 5. Examples

### 5.1 Basic Usage

```python
from pygsbox.common.progress import Progress, default_callback
from pygsbox.formats import spz

with Progress(callback=default_callback):
    hdr, data = spz.read_spz("big_model.spz")
# Output: [Read  ] [####################] 100%
```

### 5.2 Custom Callback

```python
def my_cb(phase: int, current: int, total: int) -> None:
    pct = current / max(total, 1) * 100
    print(f"Phase {phase}: {pct:.0f}%")

with Progress(callback=my_cb):
    ...  # long operation
```

### 5.3 No Callback (Silent)

```python
with Progress():  # no callback = silent
    data = spz.read_spz("model.spz")
```

## 6. Dependencies

None beyond stdlib (`sys`, `time`, `typing`).

## 7. Agent Notes

- **report() is safe to call everywhere**: No check needed — if no context is active, it's a no-op.
- **stderr for progress**: Keeps stdout clean for data output (pipe-friendly).
- **Throttle at 100ms**: Even 1M point loops will only emit ~10 updates.
- **Do not add rich/tqdm dependency**: This module must stay zero-dependency.

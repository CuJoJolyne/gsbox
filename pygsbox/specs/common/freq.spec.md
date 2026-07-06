# freq — SH / Attribute Frequency Analysis

> Auto-generated code target: `common/freq.py`

## 1. Purpose

Count frequency of unique 3-channel attribute triplets (scale, color, rotation) across a SplatData dataset. Used to estimate codebook compression potential before writing SOG/SPX with K-Means.

## 2. Public API

### `class FrequencyCounter`

#### `__init__(self) -> None`
- **Description**: Create empty counter. Uses dict keyed by `tuple[int,int,int]`.

#### `count_by_scale(self, data: SplatData) -> None`
- **Description**: Count unique `(encode_spx_scale(sx), encode_spx_scale(sy), encode_spx_scale(sz))` triplets.
- **Algorithm**: Encode scale to uint8, use `np.unique` on structured view, fill dict.

#### `count_by_color(self, data: SplatData) -> None`
- **Description**: Count unique `(R, G, B)` triplets from `data.color[:, :3]`.

#### `count_by_rotation(self, data: SplatData) -> None`
- **Description**: Count unique `(rot_x, rot_y, rot_z)` triplets from `data.rotation[:, 1:4]`.

#### `get_top_n(self, top_n: int = 256) -> Tuple[List[Tuple], List[int]]`
- **Description**: Return top-N frequent entries as (keys, counts), sorted descending.
- **Algorithm**: `sorted(self._freq.items(), key=lambda x: -x[1])[:top_n]`

#### `summary(self, top_n: int = 256) -> str`
- **Description**: Human-readable summary of codebook compression potential.
- **Output format**: `"covered: 560/5000 (11.2%), unique entries: 256, compressed size: 104.3% of original (95000 -> 99088 bytes)"`
- **Algorithm**: 
  ```
  old_bytes = total_count * 19  # 19 bytes per splat
  new_bytes = unique*3 + covered*1 + (total-covered)*4 + total*16
  ratio = 100*new_bytes / max(old_bytes, 1)
  ```

## 3. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `total_count = 0` | Summary divides by 1, returns 0% |
| `top_n > unique entries` | Returns all entries |
| Input with all identical values | Single entry with count = total |
| Random data (many unique) | Top-256 covers ~5-11% |

## 4. Examples

### 4.1 Basic Analysis

```python
from pygsbox.common.freq import FrequencyCounter
from pygsbox.core.splat_data import SplatData
import numpy as np

data = SplatData(5000)
data.color = np.random.randint(30, 225, (5000, 4), dtype=np.uint8)

fc = FrequencyCounter()
fc.count_by_color(data)
print(fc.summary(256))
# "covered: 257/5000 (5.1%), unique entries: 256, compressed size: 105.3% of original (95000 -> 99997 bytes)"
```

### 4.2 Get Top Entries

```python
keys, counts = fc.get_top_n(10)
print(keys[0])    # Most frequent (R,G,B) triplet
print(counts[0])  # Its count
```

## 5. Dependencies

| Module | Used for |
|--------|----------|
| numpy | `np.unique`, vectorized counting |
| `pygsbox.core.splat_data` | SplatData type (TYPE_CHECKING only, actual import at runtime) |
| `pygsbox.common.codec` | For scale encoding (in count_by_scale) |

## 6. Agent Notes

- **Circular import avoidance**: Use `TYPE_CHECKING` guard for SplatData import. The actual import happens when the method is called, not at module load.
- **`np.unique` with structured views**: Use `.view([('', np.uint8, 3)])` to find unique 3-byte rows efficiently.
- **Codebook compression formula**: `old_bytes = N * 19` (splat19 format), `new_bytes = dict_size*3 + covered_count*1 + (N-covered)*4 + N*16`. This is what the Go `data-freq.go` uses.

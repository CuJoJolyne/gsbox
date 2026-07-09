# pygsbox SDD（Specification-Driven Development）改造计划

## 核心理念

**Specification-Driven Development**（规约驱动开发）是基于大模型和 Code Agent 能力的现代开发范式：

- **规约（Spec）是第一资产**，代码由规约生成
- **规约即 Prompt**——人写规约，AI 写代码
- **规约即合约**——定义了模块的输入输出、行为边界、错误处理
- **规约即文档**——不再需要单独维护 API 文档
- **规-码-测三位一体**——改规约 → 重生成代码 → 重跑测试

```
传统开发：    需求 → 代码 → 测试 → 文档
SDD 开发：    规约 → (代码 + 测试 + 文档) 由 Agent 生成
              ↑                               ↓
              └── bug 修复/需求变回写规约 ─────┘
```

> 名字虽然叫 "Specification"，但这里的规约不是传统需求文档。它是**人写给 AI 看的、精准到足以生成代码的指令**。

---

## 当前状态评估

| 维度 | 现状 | SDD 目标 |
|------|------|----------|
| 模块规约 | 无——代码是唯一信息源 | 每个模块有 `*.spec.md` |
| Agent 可理解性 | 低——需读所有代码才能理解全局 | 高——读 spec 即可理解模块边界 |
| 可重生成性 | 不可能——代码和知识绑定 | 可以——改 spec 后可从零生成 |
| 测试独立性 | 部分——roundtrip 测试写死了具体格式 | 完全——测试生成于 spec 中的 example 数据 |
| 文档一致性 | 风险——文档和代码可能不同步 | 无风险——文档就是 spec，spec 生成代码 |

---

## 改造内容

### 一、目录结构

```
pygsbox/
├── specs/                         # ← 新增：所有模块的规约文件
│   ├── _template.spec.md          # 规约模板
│   ├── common/
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
│   ├── advanced/
│   │   ├── kmeans.spec.md
│   │   ├── simplify.spec.md
│   │   ├── lod.spec.md
│   │   └── autocut.spec.md
│   └── cli.spec.md
├── AGENTS.md                      # ← 新增：Agent 使用说明
├── common/
│   └── codec.py                   # 可由 codec.spec.md 重生成
├── core/
│   └── splat_data.py              # 可由 splat_data.spec.md 重生成
├── formats/
│   └── spz.py                     # 可由 spz.spec.md 重生成
├── ...                            # 其余代码文件同上
└── tests/
    └── test_basic.py              # 可由各 spec 中的 Example 自动生成
```

### 二、规约模板（`_template.spec.md`）

每个 spec 文件包含以下固定段落：

```markdown
# {模块名} — Specification

## 1. Purpose（用途）

一句话描述这个模块是干什么的。

## 2. Data Structures（数据结构）

{定义所有输入/输出类型，精确到字段类型、约束、单位}

### 2.1 Input

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| ... | ... | ... | ... |

### 2.2 Output

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| ... | ... | ... | ... |

## 3. API（接口）

{列出所有公开函数，每个函数：签名、参数、返回值、行为描述、前置条件、后置条件}

### 3.1 `function_name`

- **Signature**：`def fn(a: int, b: str) -> bool`
- **Description**：{做什么}
- **Preconditions**：{调用前必须满足的条件}
- **Postconditions**：{调用后保证成立的条件}
- **Side Effects**：{如果有 I/O、全局状态等}
- **Error Cases**：{何时抛什么异常}

## 4. Algorithm（算法）

{如果模块包含复杂算法，描述步骤、关键参数、时间复杂度}

### 4.1 主流程

```
1. 读取 header → 解析 magic + version
2. 对每个 block：
   a. 读 4 字节 block header → 判断是否压缩
   b. 解压 → 解析 count + format_id
   c. 对每种 format_id 分发到对应解码器
3. 组装 SplatData → 返回
```

### 4.2 关键常量

| 常量 | 值 | 说明 |
|------|----|------|
| ... | ... | ... |

## 5. Edge Cases（边界情况）

| 场景 | 期望行为 |
|------|---------|
| 输入为空（N=0） | {描述} |
| 输入无效 magic | 抛出 `ValueError("Invalid magic")` |
| SH degree 超出 [0,3] | 抛出 `ValueError` 或 clamp |
| ... | ... |

## 6. Examples（示例）

### 6.1 Example Data

```python
# 用于测试的示例数据
data = SplatData(3)
data.position = np.array([[1.0, 2.0, 3.0], ...])
# ...
```

### 6.2 Expected Roundtrip

```
write → read → position error < 0.01
```

## 7. Dependencies（依赖）

| 模块 | 用途 |
|------|------|
| common.codec | spz_decode_position 等编解码函数 |
| common.compress | gzip 解压 |
| core.SplatData | 输出数据结构 |

## 8. Re-generation Notes（重生成备注）

{给 Agent 的特殊提示：哪些函数必须手写、哪些可自动生成、命名约定}
```

### 三、`AGENTS.md`——Agent 使用说明书

这是一个 **给 AI Agent 读的文件**，描述项目如何工作、规约格式是什么、生成代码时应遵守的约定。

```markdown
# AGENTS.md — pygsbox Agent Guide

## Project Overview

pygsbox is a Python port of gsbox, a 3D Gaussian Splatting format conversion tool.
Supports 7 formats (.ply, .splat, .spx, .spz, .sog, .ksplat, .glb).

## Working with This Repo

### Spec-First Workflow

1. Read `specs/<module>.spec.md` to understand what to implement
2. The spec IS the source of truth — follow it exactly
3. Generate implementation in the corresponding `.py` file
4. Generate tests from the Examples section of the spec
5. Run `python tests/test_basic.py` to verify
6. Run `python -m mypy pygsbox` to pass type check

### Spec Location

- Specs live in `specs/` directory, mirroring the source tree
- `specs/common/codec.spec.md` → `common/codec.py`
- `specs/formats/spz.spec.md` → `formats/spz.py`

### Code Conventions

- Use numpy vectorized operations (avoid per-item Python loops)
- All public functions must have type hints
- Return types must match spec exactly
- Prefer `SplatData` columnar layout: position(N,3), scale(N,3), etc.
- Use `from pygsbox.common.codec import ...` for encoding/decoding

### Common Patterns

- Format reader: `header, data = format.read_xxx(path)` or `data = format.read_xxx(path)`
- Format writer: `format.write_xxx(path, data, **kwargs)`
- Error: raise `ValueError` for invalid input, never `sys.exit(1)`
- Use `from __future__ import annotations` for forward references

### Testing

- Every spec's Examples section becomes a test case
- Use `np.random.seed(42)` for reproducibility
- Assert position error < 0.01, scale error < 0.1 (unless spec says otherwise)

### Dependencies

- Required: numpy
- Optional: Pillow (for .sog, WebP blocks), zstandard (for SPZ v4), scipy (for K-Means)
- Check availability with `try/except ImportError` before using optional features
```

### 四、PROGRESS.json 扩展

新增 `specs` 字段，追踪规约→实现状态：

```json
{
  "project": "pygsbox",
  "version": "v4.8.4",
  "specs": {
    "common/codec": {"status": "implemented", "spec": "specs/common/codec.spec.md", "tests": 5},
    "common/compress": {"status": "implemented", "spec": "specs/common/compress.spec.md", "tests": 0},
    "core/splat_data": {"status": "implemented", "spec": "specs/core/splat_data.spec.md", "tests": 5},
    "core/transform": {"status": "implemented", "spec": "specs/core/transform.spec.md", "tests": 0},
    "formats/ply": {"status": "implemented", "spec": "specs/formats/ply.spec.md", "tests": 1},
    "formats/spz": {"status": "implemented", "spec": "specs/formats/spz.spec.md", "tests": 3},
    "formats/spx": {"status": "implemented", "spec": "specs/formats/spx.spec.md", "tests": 0},
    "...": "..."
  }
}
```

### 五、Spec 到代码的可重生成性评估

并非所有模块都适合"从规约完全自动生成"。评估如下：

| 模块 | Spec 可生成度 | 说明 |
|------|:---:|------|
| `common/codec` | **95%** | 纯函数，输入输出非常明确 |
| `common/compress` | **90%** | 对标准库的薄封装 |
| `core/splat_data` | **90%** | 数据结构定义 + 简单操作 |
| `formats/ply` | **80%** | 格式固定，但压缩 PLY 边角多 |
| `formats/spz` | **85%** | 格式清晰，v2/v3/v4 结构规整 |
| `formats/spx` | **70%** | 块格式多、压缩类型多、边界复杂 |
| `formats/sog` | **65%** | JSON + WebP，文件数多、交互复杂 |
| `formats/ksplat` | **80%** | 格式规整但 section 逻辑复杂 |
| `advanced/kmeans` | **75%** | 算法描述清晰但调参敏感 |
| `advanced/simplify` | **60%** | 启发式算法，调参空间大 |
| `advanced/lod` | **70%** | B-Tree 构建逻辑复杂但可描述 |
| `cli` | **40%** | 胶水代码，需人工调整 |

> **结论**：核心编解码和数据结构的生成度高于 85%，复杂算法和胶水代码生成度 50-70%。Spec 的价值不仅是代码生成——它也是 Agent 进项目时**理解全局的入口**。

### 六、实际工作量

#### Phase 1：基础设施（1 天）

| 任务 | 产出 | 工作量 |
|------|------|--------|
| 创建 `specs/` 目录树 | 目录结构 | 0.2 天 |
| 写 `_template.spec.md` | 规约模板 | 0.2 天 |
| 写 `AGENTS.md` | Agent 使用说明 | 0.3 天 |
| 更新 `PROGRESS.json` 扩展 spec 字段 | 追踪系统 | 0.3 天 |

#### Phase 2：逐模块写 Spec（3~5 天）

| 模块组 | Spec 数量 | 预估总行数 | 工作量 |
|--------|:----------:|:-----------:|--------|
| common（5 个） | 5 | ~800 行 | 1 天 |
| core（4 个） | 4 | ~600 行 | 0.5 天 |
| formats（8 个） | 8 | ~2000 行 | 2 天 |
| advanced（4 个） | 4 | ~1000 行 | 1 天 |
| cli + benchmark | 2 | ~300 行 | 0.5 天 |

#### Phase 3：验证可重生成性（1~2 天）

| 任务 | 说明 |
|------|------|
| 选 3-5 个高生成度模块 | `codec`、`splat_data`、`spz`、`ply`、`kmeans` |
| 用 Spec 重新生成代码 | 验证 "Spec → 代码 → 测试通过" 闭环 |
| 修复 Spec 中不够精准的描述 | 回写改进 |

#### 总计：**5~7 天**（单线程），**~5000 行 spec 文本**

### 七、Spec 示例（`codec.spec.md` 片段）

```markdown
# codec — Encoding/Decoding Functions

## 1. Purpose

Bit-level encoding/decoding for 3DGS attributes:
position (24-bit fixed), scale (log-space uint8), color (SH-aware uint8),
rotation (quaternion NQ), spherical harmonics (float↔uint8).

## 2. Data Structures

None. This module contains only pure functions.

## 3. API

### 3.1 `spz_decode_position`

- **Signature**: `def spz_decode_position(b: bytes, fractional_bits: int = 12) -> float`
- **Description**: Decode 3 bytes (little-endian 24-bit signed fixed-point) to float32.
- **Preconditions**: `len(b) >= 3`, `fractional_bits == 12`
- **Postconditions**: return value clipped to float32 range
- **Algorithm**:
  ```
  fixed32 = b[0] | (b[1] << 8) | (b[2] << 16)
  if fixed32 & 0x800000: fixed32 |= -0x1000000  # sign-extend
  return clip_float32(fixed32 / 4096.0)
  ```
- **Edge Cases**: ±3.4028235e+38 overflow → clip to float32 max/min

### 3.2 `spz_decode_rotations_v3v4`

- **Signature**: `def spz_decode_rotations_v3v4(bs: bytes) -> Tuple[int, int, int, int]`
- **Description**: Decode 4-byte packed NQ quaternion to uint8 quaternion (r0,r1,r2,r3).
- **Algorithm**: {详细步骤，含 bit 位域定义}
- **Edge Cases**: 
  - All zeros: return (128, 128, 128, 128) (identity rotation)
  - sum_squares >= 1.0: clamp to 1.0 before sqrt

## 4. Edge Cases

| Scenario | Behavior |
|----------|----------|
| `decode_spx_position_uint24(0,0,0)` | Returns 0.0 |
| `decode_spx_position_uint24(0xFF,0xFF,0x7F)` | Returns ~31.99 (max positive for 12-bit fractional) |
| `decode_spx_scale(0)` | Returns -10.0 (log-space min) |
| `decode_spx_scale(255)` | Returns ~5.9375 (log-space max) |

## 5. Examples

```python
# Roundtrip encode/decode
b = spz_encode_position(3.5)
assert abs(spz_decode_position(b) - 3.5) < 0.001

# NQ quaternion roundtrip  
rw, rx, ry, rz = 200, 100, 80, 150
packed = spz_encode_rotations_v3v4(rw, rx, ry, rz)
drw, drx, dry, drz = spz_decode_rotations_v3v4(packed)
# Error tolerance: NQ loses ~2 LSBs
assert all(0 <= v <= 255 for v in (drw, drx, dry, drz))
```

### 八、预期收益

| 维度 | 当前 | SDD 后 |
|------|------|--------|
| 新贡献者上手时间 | 1-2 天（需读代码） | 30 分钟（读 spec） |
| Agent 修改成功率 | ~60%（需理解全局） | ~85%（spec 隔离上下文） |
| Bug 修复正确性 | 依赖人工 review | spec 约束边界 + test 验证 |
| 文档一致性 | 手写多，易过时 | spec = 文档，永远不过时 |
| 新格式接入 | 3-5 天 | 1-2 天（先写 spec→Agent 生成→人工微调） |
| 代码重生成 | 不可能 | 可（改 spec→重新生成→跑测试） |

### 九、关键认知

1. **Spec ≠ 需求文档**。这里的 spec 是人写给 AI 看的、**精准到可以生成代码**的指令。每个字段类型、每个字节偏移、每个边界情况都要明确。
2. **80% 生成，20% 人工**。核心逻辑（编解码、数据结构）可从 spec 完全生成。胶水代码（CLI 调度、文件 IO）仍需人工。
3. **Spec 的维护**本身就是开发工作。不是"先写 spec 再写代码"，而是"写 spec **就是**在开发"。spec 是交付物，代码是产物。
4. **面向 Agent 设计**。目录结构、命名约定、注释风格，都需要让 Agent 能"一眼看懂"——这是 SDD 的工程纪律。
5. **测试 = Spec 中的 Example 段**。不是单独维护的，每次改 spec 的 Example，Agent 就同步更新测试。


---

## 十、执行结果（2026-07 更新）

### 已完成

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| Phase 1 | 基础设施（AGENTS.md, 模板, 目录树） | ✅ |
| Phase 2 | 23 个模块 spec 文件（1853 行） | ✅ |
| Phase 3 | 可重生成性验证（codec/splat_data，发现 4 个 spec 缺陷） | ✅ |
| Phase 4 | PROGRESS.json SDD 扩展（22 模块追踪） | ✅ |
| Phase 5 | Spec→测试自动生成（+6 测试，34 total） | ✅ |
| Phase 6 | 代码生成脚本（暂缓，投资收益比低） | ⏸️ |

### 关键发现

**SDD 的边界**：spec 适合做"蛋糕底座"（接口契约、数据格式标注、代码规范），但在以下场景作用有限：

1. **Go 对齐 bug**（12 个全部通过逐行读 Go 源码 + 逐字节对比发现）— spec 不可能描述这个精度级别
2. **BBF 正确性验证**（23 个 spot 正确率 6% → 自主写 benchmark 发现）— spec 不涉及算法实现细节
3. **性能优化**（numba JIT，100x 加速）— spec 不涉及性能
4. **定量验证方法论**（KD-tree + 原始字节 + 语义化误差）— spec 无法预判分析路径

**有效场景**：
- subagent 可以只读 spec + AGENTS.md 就写出正确的 `codec.py` / `splat_data.py`
- spec→test 自动生成保证了 spec 的可运行性
- AGENTS.md 的规范（numpy 向量化、SplatData 列式存储）防止 subagent 写坏架构

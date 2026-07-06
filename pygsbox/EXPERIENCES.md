# pygsbox 移植经验总结

## 项目概述

将 Go 实现的 3DGS 格式转换工具 `gsbox` 移植到 Python，覆盖 7 种格式 × 多种版本 × 高级特性（K-Means 聚类、LOD、模型简化），最终产出 28 个测试全绿、mypy 0 errors、可 `pip install` 的 Python 包。

---

## 架构决策复盘

| 决策 | 选择 | 效果 |
|------|------|------|
| **SplatData 存储** | NumPy 列式数组（非 dataclass 列表） | 百万级数据性能差 10-20x，向量化读写成为可能 |
| **编解码层** | `common/codec.py` 纯函数 | 所有格式复用同一套编解码，一致性有保障 |
| **可选依赖** | Core 只依赖 numpy，WebP/zstd/scipy 通过 `try/except` | `pip install pygsbox` 最小化，完整装用 `pip install pygsbox[full]` |
| **格式 reader/writer 对称** | 每个格式一对 `read_X` / `_write_X` | roundtrip 测试天然可做，bug 易暴露 |
| **CLI 自动识别** | 按文件后缀 dispatch，不强制指定格式 | 用户体验好，未来加格式只需扩展 switch |

> **核心经验**：NumPy 列式存储不仅是"快一点"，而是让 Python 能处理百万级数据的**前提条件**。如果当初选了 dataclass 列表，后续所有格式都要逐点 Python 循环，根本写不动。

---

## 格式移植的通用模式

移植 7 种格式（PLY/Splat/SPX/SPZ/SOG/KSplat/GLB）后沉淀出稳定套路：

1. **先读 Go 头结构**：确定 magic/version/count 等字段 → 写 Python dataclass 对应
2. **实现 `parse_*_header`**：字节级解析，所有字段类型标注
3. **实现 reader 内层**：逐块/逐点解析 payload，写入 `SplatData`
4. **跑 roundtrip 测试**：生成随机数据 → write → read → assert 位置/缩放/旋转/颜色误差阈值
5. **benchmark 暴露精度问题**：SPX v3 log encoding bug 就是 benchmark 中发现的

> **经验**：**roundtrip 测试是格式移植的生命线**。每个读者函数上线前必须有 writer + roundtrip 验证。精度阈值要根据编码类型选：24bit 定点 ~0.01，uint8 ~1，log 编码 ~0.05。

---

## 精度 Bug 诊断经验

SPX v3 位置 log encoding bug 是项目里最有价值的发现：

**现象**：Benchmark 显示 SPX v3 写读往返位置误差高达 ~12（正常应 <0.01）

**定位**：
- 先怀疑 reader 没做 `decode_log` → 发现 Python 确实漏了
- 再怀疑 Go 也漏了 → 检查发现 Go 端 `readSpxV3` 早通过 `logTimes` 参数正确处理
- 结论：只有 Python 端 bug，但根因相同（writer 的 `encode_log` 对称的 reader 端没实现）

**修复**：3 处改动：
1. `_decode_splat_from_channels` 加 `format_id` 参数
2. BF_SPLAT22/BF_SPLAT220_WEBP 时调用 `codec.decode_log(x, 1)`
3. 两处上层调用传递 `format_id`

**修复后**：误差 ~12 → ~0.001（1 万倍改进）

> **经验**：当 benchmark 发现误差数量级异常，先怀疑**对称编码是否完全对称**（encode ↔ decode 要成对出现）。Go 和 Python bug 经常在不同位置独立出现，不要想当然。

---

## mypy 集成策略

从 90 个错误降到 0，关键策略：

### 1. 渐进式宽松
```toml
[tool.mypy]
disallow_untyped_defs = false   # 不强制所有函数标注
check_untyped_defs = true       # 检查已标注函数内的代码
ignore_missing_imports = true   # 第三方库不管
```

### 2. 战略型 `type: ignore`
- numpy 返回类型推断常出 `Any`，对 `np.sqrt` / 矩阵乘法结果用 `# type: ignore[no-any-return]`
- 多态变量（如 `cli.py` 中 `hdr` 既是 `PlyHeader` 也是 `SpxHeader`）用 `hdr: Any` 声明
- 已知安全的跨类型赋值（如 dict 嵌套）用 `# type: ignore[assignment]`

### 3. 真正的 bug 要用 assert 修
- `sog.py` 中 `meta.means` 是 `Optional`，在函数开头加 `assert meta.means is not None`
- `_read_sog_v1` 中 `sh_degree > 0` 必然意味着 `meta.shN is not None`，显式 assert 帮助 mypy 做类型缩窄

> **经验**：mypy 的价值是**发现真正的逻辑漏洞**（如 None 访问、类型不匹配），而不是追求"0 警告"。对 numpy 强类型标注不要较真，但业务逻辑的类型缩窄一定要修。

---

## 进度回调的轻量设计

Go 用 `OnProgress(phase, current, total)` 全局回调，Python 用 context manager 模式更优雅：

```python
from pygsbox.common.progress import Progress, default_callback

with Progress(callback=default_callback):
    data, sh = spz.read_spz(file_path)
```

**设计要点**：
- `Progress` 用类变量 `_instance` 追踪当前上下文，读者函数内部 `Progress.report(...)` 调用时如果没上下文则无副作用
- `throttle_ms=100` 节流避免每点调用一次的开销
- `default_callback` 写 stderr，主进程 stdout 不被污染

> **经验**：进度报告要"零侵入"——reader 函数不应依赖任何 UI 库，用 context manager + 节流 callback 是最干净的解法。

---

## 测试策略

28 个测试覆盖全栈，分布：

| 类别 | 数量 | 作用 |
|------|------|------|
| 编解码 roundtrip | 5 | 验证 codec 精度 |
| 格式读写 roundtrip | 9 | 验证 format 正确性 |
| 高级特性 | 9 | K-Means / simplify / LOD / autocut |
| 数据结构 | 5 | SplatData 基本操作 |

**关键原则**：
- 每个 reader 必须配 writer，跑 roundtrip
- 用随机种子（`np.random.seed(42)`）保证可重复
- 误差阈值要根据编码类型设：
  - 24bit 定点：`<0.01`
  - uint8 颜色：`<=1`
  - log 编码：`<0.05`
  - SH 聚类：`<50`（K-Means 误差大）

---

## 性能优化经验

Benchmark 数据（200K 点）：

| 格式 | Write | Read | 说明 |
|------|-------|------|------|
| Splat | 6,874K pt/s | 2,320K pt/s | NumPy `frombuffer` + `tostring` |
| PLY | 19.6K | 288K | 读取已向量化，写入仍逐行 |
| SPX v3 | 24.9K | 13.3K | WebP 解码是瓶颈 |
| SPZ v4 | 27.4K | 34.5K | zstd 比 gzip 快 |

**核心优化手段**：
1. **NumPy 向量化**：读取 PLY 时一次 `np.frombuffer` 解析所有行，性能 10-100x
2. **`frombuffer` 复用内存**：避免拷贝原始字节
3. **gzip/xz/zstd 选择**：zstd 读 34.5K > gzip 24.8K，但 zstd 需要额外依赖

> **经验**：Python 处理大数据时，"NumPy 化"比"写 Cython"更现实。先 profile 找热点，再针对性向量化。逐点循环的 PLY 写入是已知瓶颈，但写入频率低，暂不优化。

---

## Git 提交纪律

项目期间遵守的纪律：
- **每次完成一个独立特性才提交**（如 "完成 SOG v2 SH 写出"）
- **提交前必须跑全量测试**（28/28 PASS）
- **修复 bug 时 commit message 说明根因**（如 "fix SPX v3 log encoding：reader 端漏 decode_log，误差 12→0.001"）
- **避免中间态提交**（如 mypy 还有错误时就提交会污染历史）

---

## 值得复用的代码片段

项目里沉淀了一些通用工具，可直接复用：

```python
# 1. NumPy 结构化数组定义
dtype = np.dtype([(name, np_type) for name, np_type in fields])
records = np.frombuffer(raw, dtype=dtype, count=count)

# 2. 节流进度回调
def report(self, phase, current, total):
    if time.perf_counter() - self._last < self.throttle_ms / 1000.0:
        return
    # ... callback

# 3. 格式识别 dispatch
ext = file_ext_name(path).lower()
readers = {'.ply': ply.read_ply, '.spz': spz.read_spz, ...}
return readers[ext](path)

# 4. 对称编码 roundtrip 测试
data = generate_random(N, seed=42)
write(data) -> tmpfile
hdr, data2 = read(tmpfile)
assert max_abs(data.position - data2.position) < tolerance
```

---

## 给后续维护者的建议

1. **新增格式时**：先写 roundtrip 测试再写 reader，TDD 风格
2. **改 codec.py 时**：所有格式 reader 都会受影响，必须跑全量测试
3. **改 SplatData 结构时**：所有格式 + 高级特性都受影响，要谨慎
4. **升级依赖时**：Pillow/zstd 的 minor version 可能破坏 WebP 无损编码兼容性
5. **性能回归时**：先跑 `benchmark.py`，对比基线，定位热点

---

## 最终交付清单

```
pygsbox/
├── common/              # 通用工具层
│   ├── codec.py         # 编解码函数（50+）
│   ├── compress.py      # gzip/xz/zstd/WebP/ZIP
│   ├── file_utils.py    # IO 工具
│   ├── progress.py      # 进度回调
│   ├── freq.py          # 频率统计
│   └── version_check.py # 版本检查
├── core/                # 核心数据结构
│   ├── splat_data.py    # SplatData（NumPy 列式）
│   ├── morton.py        # Morton 排序
│   ├── transform.py     # 几何变换
│   └── sh_rotation.py   # SH 球谐旋转
├── formats/             # 7 种格式读写器
│   ├── ply.py           # official/compressed/RGB
│   ├── splat.py
│   ├── spx.py           # v1/v2/v3
│   ├── spz.py           # v2/v3/v4
│   ├── sog.py           # v1/v2
│   ├── ksplat.py
│   ├── glb.py           # 3 种扩展
│   └── obj.py
├── advanced/            # 高级特性
│   ├── kmeans.py        # K-Means SH 聚类
│   ├── simplify.py      # 体素化简化
│   ├── lod.py           # B-Tree LOD
│   └── autocut.py       # autocut 管道
├── cli.py               # 命令行入口
├── benchmark.py         # 性能基准
├── __main__.py          # python -m 入口
└── tests/test_basic.py  # 28 个测试
```

**状态**：28 tests PASS · mypy 0 errors · `pip install -e .` 可用 · `dist/pygsbox.exe` 可构建

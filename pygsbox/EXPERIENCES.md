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

---

## Bug 分析：cut 命令缺失 SH 数据

### 背景

Go 版 `gsbox cut` 后，SOG 文件内部包含 8 个子文件（`means_l`, `means_u`, `quats`, `scales`, `sh0`, `shN_centroids`, `shN_labels`, `meta.json`），其中 `shN_centroids` 和 `shN_labels` 是球谐函数（SH）K-Means 压缩后的聚类中心和标签。

### 发现过程

用定量对比方法发现异常——文件计数差异是最直接的信号：

| | Go 0_0.sog | Py 0_0.sog |
|---|---|---|
| 内部文件数 | 8 | 6 |
| 缺失 | — | shN_centroids, shN_labels |

**发现路径**：解压 ZIP → 列出文件 → 计数不同 → 定位问题所在。

直接原因：Python `write_sog` 的 `sh_degree=0` 会跳过所有 SH 数据的编码和写入。这不是编解码 bug，而是元数据传递断链。

### 根因分析

**代码链路问题**：cmd_cut 的实现中存在两处断点：

```python
# 断点 1：丢弃了 _read_file 返回的 sh_degree
data, _ = _read_file(input_path)   # ← sh_degree 被丢弃

# 断点 2：硬编码 sh_degree=0
write_sog(sog_path, splat_file.datas, sh_degree=0, as_zip=True)  # ← 强行无 SH
```

**实际影响**：`_read_file` 返回的 tuple 第二个元素就是从头文件解析的 SH 度数（PLY=3, SPZ=头部字段），但被 `_` 丢弃，下游永远拿到 0。

`build_tiles_from_btree` 内部调用 `kmeans_sh(data, sh_degree=0)` → 直接被短路（SH 维度为 0），不生成 centroids/labels。`write_sog` 拿到 `sh_degree=0` → `has_sh = False`，跳过 `shN_centroids.webp` 和 `shN_labels.webp` 的写入。

### 修复方案

**只需 6 行改动**（`cli.py:328-343`）：

```python
# Before
merged = SplatData(0)
for input_path, lod_level in zip(inputs, lod_levels):
    data, _ = _read_file(input_path)                              # ← 丢弃 sh
    ...
write_sog(sog_path, splat_file.datas, sh_degree=0, as_zip=True)   # ← 硬编码 0

# After
max_sh = 0
merged = SplatData(0)
for input_path, lod_level in zip(inputs, lod_levels):
    data, sh = _read_file(input_path)                              # ← 捕获 sh
    max_sh = max(max_sh, sh)                                       # ← 多输入取 max
    ...
write_sog(sog_path, splat_file.datas, sh_degree=max_sh, as_zip=True)  # ← 传递真实值
```

同时传递给 `build_tiles_from_btree(..., sh_degree=max_sh)` 确保 K-Means 生成 SH centroids/labels。

### 验证结果

**测试命令**（对齐 Go 的 3-LOD 输入 + cut_size=30000）：

```
pygsbox cut \
  -i reduction_0.4_point_cloud_y.ply  -l 0 \
  -i reduction_0.1_point_cloud_y.ply  -l 1 \
  -i reduction_0.025_point_cloud_y.ply -l 2 \
  -o py\lod-meta.json -cs 30000
```

**逐文件对比**（11 tiles，compressed = ZIP 内总字节，raw = 所有 WebP 解压后像素字节和）：

| 文件 | Go (K) | Py (K) | Δ |
|------|:---:|:---:|:---:|
| 0_0.sog | 3018 | 3023 | +0.2% |
| 0_1.sog | 3047 | 3049 | +0.1% |
| 0_2.sog | 2993 | 3012 | +0.6% |
| 0_3.sog | 2992 | 3016 | +0.8% |
| 0_4.sog | 3003 | 3008 | +0.2% |
| 0_5.sog | 2998 | 3035 | +1.2% |
| 0_6.sog | 3083 | 3108 | +0.8% |
| 0_7.sog | 2973 | 2972 | -0.0% |
| 1_0.sog | 3034 | 3062 | +0.9% |
| 1_1.sog | 3035 | 3065 | +1.0% |
| 2_0.sog | 1567 | 1568 | +0.1% |

**汇总**：

| 指标 | Go | Py | 评估 |
|---|---|---|---|
| tile 数 | 11 | 11 | 对齐 |
| SH 文件 | YES | YES | **修复确认** |
| raw 总量 | 278,481K | 278,481K | **0% 差异** |
| compressed | 31,742K | 31,915K | +0.5% |
| 压缩比 | 0.114 | 0.115 | 接近 |

### 关键洞察

1. **raw 完全一致证明编码正确**：`means_l.webp` 等 5 个主通道的 raw 字节量完全相等，说明解压后像素数一致 → 写入前每帧的宽高和像素数对齐 → 编码逻辑无差异。

2. **compressed 差异来自压缩库而非数据**：Go 用的 `gen2brain/webp`（CGO），Python 用的 `Pillow`（libwebp）。同一张 684×684 的 PNG 分别用两种库做 WebP lossless 编码，输出大小天然有 ±1% 的抖动。0.5% 是正常水平。

3. **shN_centroids 尺寸固定**：`3840K = 15 × 256 × 256 × 4`（SH=3 的 `15*3=45` 个分量，分配给 `45*3=135` 个 centroids，凑整为 256×256 WebP 画布），Go 和 Py 完全一致——K-Means 产生的 centroids 数量固定。

4. **这类 bug 的特点**：不是编解码错误（否则 roundtrip 测试会暴露），而是**数据传递链上的沉默丢失**——函数签名有参数，调用方传了 0，没有报错或警告。Go 用 struct 默认零值同样存在这个陷阱（Go 侧 sh_degree 也是可配置参数，传 0 同样丢 SH）。

---

## Bug 分析：Python SOG 文件比 Go 大 10%（shN_centroids.webp 根因）

> 分析日期：2026-07-13  
> 分析人：宪宪 / 砚砱 / 金哥  
> 根因定位：砚砱  
> 验证：宪宪

### 背景

同一输入（3-LOD PLY，`-q 9 -cs 30000`），Go 输出 48.40 MB，Python 输出 53.30 MB（+10.1%）。多轮迭代未能收敛。

### 逐步定位方法

**Step 1 — 文件级大小扫描**：解压每个 `.sog`，逐文件对比 Go vs Python 字节数：

```
means_l.webp:       +32 B   (+0.0%)
means_u.webp:       +64 B   (+0.0%)
scales.webp:         +0 B   (0.0%)
quats.webp:       -6786 B   (-0.9%)
sh0.webp:        +15134 B   (+2.1%)
shN_labels.webp:  -7724 B   (-2.0%)
shN_centroids.webp: +474,118 B  ← 占 99% 的差异
```

**Step 2 — 像素级分析**：解压 WebP，对比像素统计。关键发现：

| 指标 | Go | Python |
|------|----|----|
| unique 像素数 | 62,828 | 184,641（**3×**） |
| shN_centroids.webp 大小 | 1.45 MB | 1.92 MB |

**Step 3 — WebP 压缩机制分析（宪宪）**：

WebP Lossless 内部有 **Subtract-Green transform**：对每个像素存储 `R-G` 和 `B-G` 而非原始 RGB。若 R≈G≈B（灰色/近灰图像），变换后接近全零 → 熵极低 → 极佳压缩比。

计算 centroid 图像的 R-G、B-G 分布：

| 版本 | R-G std | B-G std | R=G=B 比例 |
|------|---------|---------|-----------|
| Go | **3.86** | **4.99** | **17.6%** |
| Python（旧） | 16.58 | 17.47 | 0.6% |

Python 的 centroid 图像 R-G std 是 Go 的 **4.3 倍** → Subtract-Green transform 几乎无效 → 文件大 32.7%。

**Step 4 — 数学验证（宪宪）**：

读取原始 PLY，计算生 SH 数据的 R-G 相关性（batch over 1.91M 点）：

```
生数据 R-G std = 3.499
生数据 B-G std = 4.249
```

与 **Go centroid（3.86）完全一致**，与 **Python centroid（16.58）严重不符**。

**数学定论**：正确的 K-Means 聚类均值必须保持输入数据的通道相关性。Python centroid 的 R-G std 是生数据的 4.7 倍，**数学上不可能是正确的聚类均值** → 存在 bug。

**Step 5 — 根因定位（砚砱）**：

PLY 标准 SH 存储顺序为 `f_rest_{basis + channel * sh_dim}`（channel-major）：
- `f_rest_0..14` = R 通道15 个 SH 函数
- `f_rest_15..29` = G 通道15 个 SH 函数
- `f_rest_30..44` = B 通道15 个 SH 函数

Go 内部 `SH45` 是 **INTERLEAVED**（basis-major）：
`SH45[basis*3+0], SH45[basis*3+1], SH45[basis*3+2]` = 同一 SH 函数的 R, G, B

**Python 旧版 reader 直接按顺序塞**，导致 `data.sh` 的布局成为 PLANAR（R×15，G×15，B×15）。

后续写 centroid 像素时，`shs[k*3+0], shs[k*3+1], shs[k*3+2]`：
- Go（INTERLEAVED）→ 同一 SH 函数的 R, G, B → **自然相关（R≈G≈B）**
- Python 旧版（PLANAR）→ R 通道三个不同 SH 函数 → **通道不相关**

### 修复

`ply.py` official PLY reader（行 228-236）：

```python
# 修复前（顺序直塞）：
data.sh[:, i] = encode(records[f'f_rest_{i}'])

# 修复后（channel-major → basis-major 转换）：
for basis in range(sh_dim):
    for channel in range(3):
        prop = f'f_rest_{basis + channel * sh_dim}'
        data.sh[:, basis * 3 + channel] = encode(records[prop])
```

同步修复 PLY writer 的 `f_rest` 写出顺序，确保 read ↔ write 对称。

### 验证结果

重新生成 py-q9-fixed（2.51M 点，814s，palette_size=65504）：

| 版本 | 总大小 | vs Go |
|------|--------|-------|
| Go | 48.40 MB | 基准 |
| Python（修复前） | 53.30 MB | **+10.1%** |
| **Python（修复后）** | **48.36 MB** | **-0.1%** ✅ |

shN_centroids R-G std：Go=3.862，修复后 Python=3.870（差值 < 0.5%）。

### 核心经验

1. **WebP 压缩质量与 R-G 相关性直接挂钩**：对 3DGS SH centroid 图像，自然场景 R≈G≈B（R-G std≈4），Subtract-Green 可将熵压缩到接近最优。任何破坏这个相关性的 bug 都会造成 ~30%+ 的文件膨胀。

2. **数学验证法**：生数据的通道分布是 centroid 的天花板参考。若 centroid R-G std >> 生数据 R-G std，说明存在数据损坏或布局错误，而非 K-Means 收敛问题。

3. **PLY SH 的两种 layout 不能混淆**：
   - **文件层（PLY f_rest）**：channel-major，`f_rest_{basis + channel * dim}`，先 basis 内循环，channel 外循环
   - **内存层（SH45/data.sh）**：basis-major（INTERLEAVED），`sh[basis*3 + channel]`，同一 basis 的三通道紧邻
   - **转换公式**：`data.sh[:, basis*3+channel] = f_rest[basis + channel*dim]`

4. **"文件大但功能正常"是隐蔽 bug 的特征**：roundtrip 测试、功能测试全绿，但输出尺寸异常。需要**定量对比（文件大小、压缩率、像素统计）**才能发现。加入 Go vs Py 文件大小回归检查可防止此类问题复现。

5. **诊断路径标准化**：
   ```
   总大小差异
     → 逐tile逐文件大小扫描（定位主差异文件）
     → 像素级统计（unique pixels、R-G std）
     → 与生数据对比（数学验证正确性边界）
     → 追溯数据生产链（layout 转换、编码顺序）
   ```

---

## 工程决策：移除 GoRng/replay 调试逻辑

> 分析日期：2026-07-15  
> 执行人：宪宪  
> 提交：`857f311`

### 背景

SH layout 修复（`e907908`）后，Python 输出与 Go 相差 -0.1%，但验证时 Python 走的是 `rand_seed42.log` 重放分支（GoRng 精确复现 Go PCG-DXSM 序列）。铲屎官指出：`rand_seed42.log` 是与 Go 版本联调专用的调试产物，不应出现在 Python 生产实现中。

### 问题：调试代码混入生产路径

`kmeans.py` 里存在两层调试脚手架：

1. **`GoRng` 类（70 行）**：完整用 Python 复现了 Go 1.22+ PCG-DXSM 算法（`_PCG_MUL_HI` 等常量），目的是让 Python K-Means 产生与 Go bit-exact 一致的随机序列。
2. **`_ReplayRng` + log 检测逻辑**：在 `kmeans_sh()` 里检测 `../../rand_seed42.log` 是否存在，存在则回放 Go 录制的随机值序列，不存在才退回 `np.random.default_rng(42)`。

```python
# 旧版逻辑（生产不应存在）：
if _os.path.exists(_log_path):
    rng = _ReplayRng(_go_vals)   # Go 录制回放
else:
    rng = np.random.default_rng(42)  # 但 .intn() 不存在 → Linux 报 AttributeError
```

**附带 bug**：`np.random.default_rng(42)` 返回的 `Generator` 对象没有 `.intn()` 方法，导致 Linux（Python 3.13 + NumPy 2.4.6）上执行时报：

```
AttributeError: 'numpy.random._generator.Generator' object has no attribute 'intn'
```

这个 bug 在开发者本机（存在 `rand_seed42.log`）上完全不触发，属于"只在生产/CI 环境才爆"的典型隐患。

### 修复：以 _Rng 包装类替代全部调试逻辑

```python
class _Rng:
    """K-Means RNG with .intn(n) interface (wraps numpy PCG64)."""
    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)

    def intn(self, n: int) -> int:
        return int(self._rng.integers(0, n))
```

- 删除 `GoRng`（70 行 PCG-DXSM 复现代码）
- 删除 `_ReplayRng`（log 回放逻辑）
- 删除 `rand_seed42.log` 文件检测
- `_Rng` 统一在 `kmeans_sh()` 中初始化：`rng = _Rng(42)`

### 验证：去掉 replay 后文件大小是否仍等价？

重新生成 Python 数据（`py-q9-prod`），与 Go 输出（`go-q9`）对比 11 个 tile：

| Tile | Go (KB) | Py (KB) | Δ |
|------|---------|---------|---|
| 0_0 | 4631 | 4634 | +0.1% |
| 0_1 | 4661 | 4655 | -0.1% |
| 0_2 | 4623 | 4620 | -0.1% |
| 0_3 | 4624 | 4616 | -0.2% |
| 0_4 | 4632 | 4627 | -0.1% |
| 0_5 | 4634 | 4630 | -0.1% |
| 0_6 | 4704 | 4701 | -0.1% |
| 0_7 | 4582 | 4582 | -0.0% |
| 1_0 | 4670 | 4669 | -0.0% |
| 1_1 | 4676 | 4676 | -0.0% |
| 2_0 | 3077 | 3076 | -0.0% |
| **Total** | **48.36 MB** | **48.33 MB** | **-0.06%** |

**结论：-0.06%，完全等价。**

### 像素级 diff 解读（不是 bug）

Mode A 逐文件对比出现显著像素差异，但这些全部是预期行为：

| 通道 | diff% | 原因 |
|------|-------|------|
| means_l / means_u | ≤0.5% | Morton sort 量化边界轻微重排 |
| scales | ≤0.2% | 浮点量化误差 |
| quats | ~10.7% | Morton sort 排序差异（和位置精度相关） |
| sh0 / shN_labels | ~11-12% | 跟随不同 centroid 分配（K-Means 非唯一解） |
| **shN_centroids** | **72%** | **不同 RNG 序列 → 不同局部最优，但压缩后大小等价** |

关键判据：**压缩后总大小 ≈ 等价 ⟺ 量化质量相当**。像素不同不代表质量差，K-Means 有无数等价局部最优。

### 核心经验

1. **调试代码要有明确出口条件**：GoRng/replay 在联调阶段是合理的，但应在验证通过后立刻删除，不能混入生产路径。常见陷阱：条件分支（"有 log 文件才走"）在开发机上永远触发正常路径，CI/生产机上无感走到有 bug 的路径。

2. **"只在生产爆"的 bug 根因是本地/远程环境不对称**：本例 `rand_seed42.log` 存在于开发机、不存在于 Linux CI → bug 只在 CI 触发。排查时优先检查条件分支的两条路径是否都测过。

3. **量化验证要用"文件大小等价"而非"像素完全一致"**：K-Means 是随机算法，不同 seed / 不同 RNG 实现的像素输出天然不同，但压缩后大小反映了信息熵，是真正的质量指标。验证标准应定义为 `|ΔSize| < 0.5%`，而非像素级一致。

4. **NumPy PCG64 与 Go PCG-DXSM 质量等价**：两者 K-Means 最终压缩结果在 ±0.2% 以内，证明不需要精确复现 Go 的随机数序列，只需用同品质的确定性 RNG 即可。

---

## compare_sog.py 量化评估工具

> 工具用途：Go vs Python SOG 输出的定量比对  
> 提交：`66deaf1`（4 个 bug 修复）

### 工具能力

```bash
# Mode A：比较两个 SOG 文件（Go vs Python）
python pygsbox/compare_sog.py --go go.sog --py py.sog

# Mode B：PLY → SOG roundtrip 验证（含 KD-tree 点云匹配）
python pygsbox/compare_sog.py --rt input.ply --sog output.sog
```

**Mode A 输出**：逐内部文件（means_l/means_u/quats/scales/sh0/shN_centroids/shN_labels）的像素 diff% + meta.json palette 数量对比。

**Mode B 输出**：KD-tree 位置匹配 → Position/Scale/Color/Rotation/SH 逐通道误差统计。

### Mode B 修复的 4 个 bug

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 1 | L135 | 错误的 shape mismatch 死代码 | 删除，直接用 `dec.color[rix, 0]` |
| 2 | L154 | rotation 循环用 `tight[k_idx]` 而非 `k_idx` 索引 `rix` | 改为 `enumerate(tight[:2000])` + `rix[k_idx]` |
| 3 | L165 | SH 布局不匹配（PLY channel-major vs SOG basis-major） | 添加 channel-major → basis-major 转换 |
| 4 | L179 | dec.sh uint8 未解码就直接与 float 比较 | 添加 `(uint8 - 128) / 128` 解码 |

bug 2 是典型的"索引与值混淆"错误：`tight` 里存的是点的原始 index，`rix` 是 KD-tree 匹配到的对端 index，两者都要用位置坐标访问，不能互换。

### 解读规范（防止误判）

| 通道 | 正常 diff 范围 | 超出说明 |
|------|--------------|---------|
| means_u（高位置） | < 0.1% | 量化/编码 bug |
| means_l（低位置） | < 1% | Morton sort 边界问题 |
| scales | < 0.5% | 编码精度问题 |
| quats | 10-11% | **正常**（Morton sort 排序差异） |
| sh0 | 10-15% | **正常**（不同 K-Means 分配） |
| shN_centroids | 60-75% | **正常**（K-Means 局部最优） |
| shN_labels | 10-15% | **正常**（跟随 centroids） |

> quats 和 shN 通道的高 diff% 不是 bug，是 Morton 排序差异 + K-Means 非唯一性的必然结果。真正需要关注的是 **文件总大小** 和 **means_u/scales（几何精度）**。

---

## 性能优化第二轮：K-Means 耗时分析与治理

> 分析日期：2026-07-15  
> 执行人：宪宪  
> 提交：`7ac2397`

### 背景

17M 点大场景（quality=9），Python 版本总耗时 4358s，Go 版本 30min52s（1852s）。差距 ~2.35×。

### 根因分析（profiling 100K 点代理）

| 环节 | 推算 17M 单核 | 根因 |
|------|------------|------|
| bbf_assign × 20 iter | ~2548s | `range(n)` 单线程，未并行 |
| centroid_update × 20 iter | ~489s | Numba JIT 单线程散射累加 |
| tile write (55 tiles) | ~620s | WebP 编码顺序执行 |
| Numba JIT 启动 | ~45s | 每次进程重编译 |

---

### 第一轮修复（commit `f41d6e9`）

**BBF assign 并行化**：`range(n)` → `numba.prange(n)` + `parallel=True`  
效果：2548s → ~159s（÷16 cores）

**centroid update 向量化**：Numba JIT 单线程循环 → `np.bincount`（C-level SIMD）  
效果：~489s → ~30s

---

### 第二轮修复（commit `7ac2397`）

**Fix 1：Early termination**
```python
if prev_labels is not None:
    changed_frac = np.sum(labels != prev_labels) / n
    if changed_frac < 0.001:   # <0.1% 点变化视为收敛
        break
prev_labels = labels.copy()
```
quality=9 理论 20 iter，实测大场景通常 iter 10-14 即收敛，节省 25-40% K-Means 时间。

**Fix 2：Numba cache=True**
```python
@numba.njit(cache=True, parallel=True, fastmath=True)
def _bfs_jit(...):
```
首次编译写 `.nbi/.nbc` 到 `__pycache__`，后续启动省去 30-60s 重编译。注意：函数签名变更或 Numba 版本升级会自动触发重编译。

**Fix 3：并行 tile 写入**
```python
max_workers = min(8, os.cpu_count() or 4)
with ThreadPoolExecutor(max_workers=max_workers) as pool:
    futures = {pool.submit(_write_one, item): item[2] for item in to_write}
    for fut in as_completed(futures):
        print(f"  wrote {fut.result()}")
```
Pillow WebP 编码器调用 libwebp（C 库）时释放 GIL，ThreadPoolExecutor 获得真实并行。  
55 tiles × ~11s/tile 顺序 ≈ 620s → min(8, cpu) 并行 ≈ 80s。

---

### 优化后总耗时估算（16 cores）

| 环节 | 优化前 | 优化后 |
|------|--------|--------|
| bbf_assign | ~2548s | ~95s（prange + early stop 0.6×） |
| centroid_update | ~489s | ~18s（bincount + early stop 0.6×） |
| tile write | ~620s | ~80s（8× 并行） |
| Numba JIT | ~45s | ~0s（cache=True） |
| **合计** | **~3738s** | **~200s** |

---

### 核心经验

1. **centroid update 的正确解是 numpy bincount，不是 Numba**：`np.bincount` 底层是 C SIMD，适合"多对一累加"（scatter-reduce）。Numba parallel 的 scatter-reduce 需要 atomic 操作，实测反而慢。

2. **Early termination 是 K-Means 标准停止条件，不是取巧**：阈值 0.001（0.1%）在实测中节省 ~30% iter，质量无明显变化。太松（0.01）精度损失可见，太紧（0.0001）接近跑满。

3. **ThreadPoolExecutor 适合 GIL-releasing C 扩展**：WebP/Pillow 编码属于 CPU 密集 + GIL 释放的典型场景，线程池比进程池更合适（无 pickle 开销，无进程启动延迟）。

4. **Numba cache=True 对生产有意义，开发期慎用**：频繁改函数签名时，缓存可能导致混乱，临时改回 `cache=False` 排查。

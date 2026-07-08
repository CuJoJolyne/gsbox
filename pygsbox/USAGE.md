# pygsbox

Python 版 3DGS 格式转换工具，完整移植自 Go 版 [gsbox](https://github.com/gotoeasy/gsbox)。支持 7 种主流 3DGS 格式的读写、模型简化、LOD 生成、顶点变换，并提供可编程 Python API。

<p align="center">
    <a href="https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/"><img src="https://img.shields.io/badge/model-3DGS-brightgreen.svg"></a>
    <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg"></a>
    <a href="https://github.com/gotoeasy/gsbox"><img src="https://img.shields.io/badge/origin-gsbox-orange.svg"></a>
</p>

---

## 功能特性

- [x] 格式转换：`.ply`、`.splat`、`.spx`、`.spz`、`.sog`、`.ksplat`、`.glb` 互转
- [x] 查看文件信息：支持上述所有格式
- [x] 数据变换：旋转 (Rot)、缩放 (Scale)、平移 (Trans)
- [x] 模型简化：体素网格合并，减少点数量
- [x] LOD 生成：构建 B-Tree 层次化 `lod-meta.json`
- [x] 自动 LOD：一键生成多级简化 + 空间切分
- [x] OBJ 顶点变换：对 `.obj` 文件做旋转/缩放/平移
- [x] HTTP 输入：支持从 URL 下载文件后直接转换
- [x] 进度显示：转换过程实时显示进度条
- [x] **numba JIT 加速**：K-Means SH 聚类接近 Go 编译性能
- [x] **完整 Go 对齐**：splat/SPZ/SPX/PLY/SOG 格式与 Go 实现逐字节验证通过

---

## 支持的格式

| 格式            | 读 | 写 | 参考                                                                            |
|----------------|:-:|:-:|--------------------------------------------------------------------------------|
| `.ply`（标准）  | ✅ | ✅ | [3DGS 官方 PLY](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/)     |
| `.compressed.ply`| ✅ | ✅ | [SuperSplat](https://github.com/playcanvas/supersplat)                         |
| `.splat`       | ✅ | ✅ | [splat viewer](https://github.com/antimatter15/splat)                          |
| `.spx` v1/v2/v3| ✅ | ✅ | [SPX 规范](https://github.com/reall3d-com/Reall3dViewer/blob/main/SPX_EN.md)   |
| `.spz` v2/v3/v4| ✅ | ✅ | [spz](https://github.com/nianticlabs/spz)                                      |
| `.ksplat`      | ✅ | ⬜ | [GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D)              |
| `.sog` v2      | ✅ | ✅ | [PlayCanvas SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/) |
| `lod-meta.json`| ✅ | ✅ | [LOD Streaming](https://developer.playcanvas.com/user-manual/gaussian-splatting/building/unified-rendering/lod-streaming/) |
| `.glb`         | ✅ | ✅ | [KHR_gaussian_splatting](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_gaussian_splatting) |

> ℹ️ **SPX 格式**：支持 v1（gzip）、v2（gzip/xz）、v3（gzip/xz + WebP block）三个版本，v3 是推荐格式。
> 
> ℹ️ **SPZ 格式**：支持 v2/v3（gzip 压缩）和 v4（zstd 流压缩），v4 是推荐格式。

---

## 安装

### 方式 1：pip 安装（推荐）

```bash
# 基础安装（仅 numpy）
pip install .

# 完整安装（含 WebP + zstd + scipy + numba）
pip install ".[full]"

# 可选依赖
pip install Pillow zstandard scipy numba
#   Pillow:    WebP 支持（SOG/SPX-WebP 块）
#   zstandard: zstd 压缩（SPZ v4）
#   scipy:     cKDTree 加速（K-Means，低维 SH）
#   numba:     JIT 编译（K-Means，所有维度，推荐）
```

### 方式 2：开发模式

```bash
git clone https://github.com/gotoeasy/gsbox
cd gsbox
pip install -e .
```

### 方式 3：单文件 exe（无需 Python）

```bash
# Windows
python .\build.py

# 生成的 exe 位于 dist/pygsbox.exe
dist\pygsbox.exe --help
```

### 方式 4：模块运行

```bash
python -m pygsbox --help
```

---

## 命令行用法

```bash
pygsbox <command> [options]
```

### 命令一览

| 命令 | 说明 |
|------|------|
| `convert` | 格式转换（自动识别输入/输出格式） |
| `info` | 打印文件信息（点数、SH 等级等） |
| `simplify` | 模型简化（体素合并） |
| `lod` | 构建 LOD B-Tree 结构 |
| `autocut` | 自动多级简化 + 空间切分 + LOD |
| `obj` | OBJ 文件顶点变换 |
| `check_update` | 检查最新版本 |

### 快捷命令（同 `convert`）

| 快捷方式 | 等价命令 |
|---------|---------|
| `p2s`、`ply2splat` | ply → splat |
| `p2z`、`ply2spz` | ply → spz |
| `p2g`、`ply2glb` | ply → glb |
| `p2p`、`ply2ply` | ply → ply |
| `z2p`、`spz2ply` | spz → ply |
| `z2g`、`spz2glb` | spz → glb |
| `g2p`、`glb2ply` | glb → ply |
| ...   | 其他组合同理，按后缀 dispatch |

### 通用选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `-i, --input` | 输入文件路径（支持 HTTP URL） | — |
| `-o, --output` | 输出文件路径 | — |
| `-sh <0-3>` | 输出 SH 球谐等级 | 保持原值 |
| `-a <0-255>` | alpha 过滤阈值 | 0 |
| `-rx <deg>` | 绕 X 轴旋转角度 | 0 |
| `-ry <deg>` | 绕 Y 轴旋转角度 | 0 |
| `-rz <deg>` | 绕 Z 轴旋转角度 | 0 |
| `-s <factor>` | 统一缩放因子 | 1.0 |
| `-tx <val>` | X 轴平移 | 0 |
| `-ty <val>` | Y 轴平移 | 0 |
| `-tz <val>` | Z 轴平移 | 0 |
| `-to <order>` | 变换顺序 RST/RTS/SRT/STR/TRS/TSR | RST |
| `-ov <num>` | SPZ 输出版本号 (2/3/4) | 4 |
| `-ov <num>` | SPX 输出版本号 (1/2/3) | 3 |
| `-bf <num>` | SPX 块格式 (22/23/220/230) | 220 |
| `-q <1-100>` | WebP 编码质量 | 90 |
| `-cs <num>` | LOD B-Tree 叶节点大小 | 102400 |

---

## 示例

### 格式转换

```bash
# ply → splat
pygsbox p2s -i /path/to/input.ply -o /path/to/output.splat

# ply → spz（不保留 SH）
pygsbox p2z -i /path/to/input.ply -o /path/to/output.spz -sh 0

# ply → spz v3（zstd 压缩）
pygsbox p2z -i /path/to/input.ply -o /path/to/output.spz -ov 3

# ksplat → spz v4
pygsbox convert -i /path/to/input.ksplat -o /path/to/output.spz -ov 4

# ply → spx（默认 WebP 块，推荐格式）
pygsbox ply2spx -i /path/to/input.ply -o /path/to/output.spx

# ply → spx（指定块格式 + 质量）
pygsbox ply2spx -i /path/to/input.ply -o /path/to/output.spx -bf 220 -q 85

# ply → glb（KHR_gaussian_splatting 扩展）
pygsbox ply2glb -i /path/to/input.ply -o /path/to/output.glb

# sog → ply
pygsbox g2p -i /path/to/input.sog -o /path/to/output.ply

# 带变换：spx → spz（旋转 90° + 缩放 0.9 + 平移 0.1）
pygsbox convert -i /path/to/input.spx -o /path/to/output.spz -rz 90 -s 0.9 -tx 0.1 -to TRS
```

### 远程文件转换

```bash
# 直接从 HTTP URL 读取并转换
pygsbox convert -i https://example.com/model.spz -o output.ply
```

### 查看文件信息

```bash
pygsbox info -i /path/to/file.spx
# 输出:
# File: /path/to/file.spx
# Format: SPX v3
# Splat count: 1234567
# SH degree: 3
```

### 模型简化

```bash
# 简化：输出点数通常减少 30-70%
pygsbox simplify -i /path/to/input.ply -o /path/to/output.ply
```

### LOD 生成

```bash
# 构建 B-Tree LOD 结构
pygsbox lod -i /path/to/input.ply -o /path/to/lod-meta.json -cs 30000

# 自动 LOD：多级简化 + 空间切分（推荐）
pygsbox autocut -i /path/to/input.ply -o /path/to/lod-meta.json
```

### OBJ 顶点变换

```bash
# 旋转 OBJ 文件
pygsbox obj -i /path/to/input.obj -o /path/to/output.obj -rx 90 -ry 45

# 缩放 + 平移
pygsbox obj -i /path/to/input.obj -o /path/to/output.obj -s 2.0 -tx 1.0 -ty -0.5
```

### 检查更新

```bash
pygsbox check_update
```

---

## Python API

pygsbox 也可以作为 Python 库编程调用，适合批量处理和自动化场景。

### 基础读写

```python
from pygsbox.formats import ply, splat, spx, spz, sog, glb
from pygsbox.core import splat_data, morton

# 读 PLY
header, data = ply.read_ply("input.ply")
print(f"Loaded {data.count} splats, SH degree: {header.max_sh_degree()}")

# 做任意处理（变换、过滤、简化等）

# 写 SPZ v4
spz.write_spz("output.spz", data, sh_degree=1, version=4)

# 写 SPX v3（推荐格式）
spx.write_spx("output.spx", data, version=3, block_format=spx.BF_SPLAT220_WEBP, quality=90)
```

### 数据变换

```python
from pygsbox.core import transform

# 旋转
transform.rotate(data, rx=90, ry=45, rz=0)

# 统一缩放
transform.scale(data, 0.5)

# 平移
transform.translate(data, tx=1.0, ty=-0.5, tz=2.0)
```

### 模型简化

```python
from pygsbox.advanced.simplify import simplify

# 直接调用函数（可调节 grid_size_factor 控制简化强度）
simplified = simplify(data, grid_size_factor=3.0)
print(f"{data.count} -> {simplified.count} splats")
```

### K-Means SH 聚类

```python
from pygsbox.advanced.kmeans import rewrite_sh_by_kmeans

# 返回 (centroids, labels, palette_size)
# 聚类后 SH 系数共享，文件体积大幅下降
centroids, labels, palette_size = rewrite_sh_by_kmeans(data, sh_degree=1, iterations=5)
print(f"Palette entries: {palette_size}")
```

### LOD 生成

```python
from pygsbox.advanced.lod import build_btree, build_tiles_from_btree, lod_meta_to_json

# 构建 B-Tree
root = build_btree(data, cut_size=102400)
tiles, meta = build_tiles_from_btree(data, root, lod_levels=1)

# 导出 JSON
json_str = lod_meta_to_json(meta)
with open("lod-meta.json", "w") as f:
    f.write(json_str)
```

### 自动 LOD（多级简化 + 空间切分）

```python
from pygsbox.advanced.autocut import autocut

autocut(data, "lod-meta.json", lod_levels=5, sh_degree=1)
```

### 进度回调

```python
from pygsbox.common.progress import Progress, default_callback

with Progress(callback=default_callback):
    data, sh = spz.read_spz("big_model.spz")
# 输出: [Read  ] [####################] 100%
```

---

## 性能参考

基于 benchmark（200K 点，单核 3.0Ghz CPU）：

| 格式 | 写入 | 读取 | 备注 |
|------|------|------|------|
| Splat | 6,874K pt/s | 2,320K pt/s | 最快，未压缩 |
| PLY | 19.6K pt/s | 288K pt/s | 读取已 NumPy 向量化 |
| SPX v3 | 24.9K pt/s | 13.3K pt/s | WebP 块解码慢 |
| SPZ v4 | 27.4K pt/s | 34.5K pt/s | zstd 比 gzip 快 |
| SOG v2 | 22.3K pt/s | 28.1K pt/s | WebP 编码 |

### 真实数据测试（119K 点，SH3，ply→sog）

| 版本 | -q 5 (KI=10) | -q 9 (KI=20) | vs Go |
|------|:---:|:---:|:---:|
| Go 原版 | 35s | 334s | — |
| Python (numba) | 40s | 140s | 1.14x / 2.4x 快 |

> ⚠️ 写入性能瓶颈在 Python 逐点循环，后续可考虑 Cython 优化。

---

## 已知局限

- **KSplat 只读**：Go 版同样只读，Python 保持一致。
- **SPX 块压缩**：仅支持 gzip 和 xz，不支持私有压缩格式。
- **合并多文件**：未实现 `join` 命令（Go 版 `-i` 多输入）。
- **数据打印**：未实现 `printsplat` 命令。
- **无 numba 时 K-Means 慢 7x**：纯 Python BBF 比 Go 慢 7x，`pip install numba` 后仅慢 1.14x。

---

## 依赖

**必选**：
- Python >= 3.10
- numpy >= 1.24

**可选**：
- `Pillow >= 10.0`：WebP 编解码（SOG 格式 + SPX WebP 块必需）
- `zstandard >= 0.21`：zstd 压缩（SPZ v4 必需）
- `scipy >= 1.10`：KD-Tree 加速（K-Means 低维 SH）
- `numba >= 0.60`：JIT 编译（K-Means 所有维度，**强烈推荐**，100x 加速）

---

## 测试

```bash
# 运行全部测试（34 个，覆盖所有格式 roundtrip + 高级特性）
python tests/test_basic.py

# 运行性能基准
python pygsbox/benchmark.py
```

---

## 许可证

本项目继承自 [gsbox](https://github.com/gotoeasy/gsbox) 的许可证。

---

## 致谢

- 原版工具：[gotoeasy/gsbox](https://github.com/gotoeasy/gsbox)
- 3DGS 论文：Kerbl et al., *3D Gaussian Splatting for Real-Time Radiance Field Rendering* (SIGGRAPH 2023)
- 格式规范：[SuperSplat](https://github.com/playcanvas/supersplat)、[splat](https://github.com/antimatter15/splat)、[Reall3d SPX](https://github.com/reall3d-com/Reall3dViewer/blob/main/SPX_EN.md)、[Niantic SPZ](https://github.com/nianticlabs/spz)、[PlayCanvas SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/)

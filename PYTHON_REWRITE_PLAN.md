# Python 重写 gsbox 工作量分析

## 一、整体评估

| 维度 | Go 现状 | Python 重写估计 |
|------|---------|-----------------|
| 代码量 | ~15000 行 | ~12000-18000 行 |
| 性能 | 编译型，原生快 | 解释型，瓶颈需 C 扩展/NumPy/多线程 |
| 部署 | 单二进制跨平台 | 需打包（PyInstaller/cx_Freeze）或 `pip install` |

**核心风险：** 性能敏感路径（大文件读写、K-Means、WebP 编解码）在 Python 中可能慢 10-100 倍，需要用 NumPy/向量化/C 扩展弥补。

---

## 二、工作拆解（按模块）

### Phase 1：基础设施 — `cmn/` → `common/`

| 子任务 | Go 来源 | Python 等价方案 | 工作量 | 难度 |
|--------|---------|-----------------|--------|------|
| 命令行解析 | `os_args.go` 自定义解析器 | `argparse` 或 `click`，但需适配 `-i` 多值等自定义行为 | 中 | 低 |
| 数值编解码 | `common.go` 各类 float↔uint 编解码 | `struct` 模块 + `numpy` 向量化，或纯 Python bit 操作 | 大 | 中 |
| 压缩：gzip | `compress_gzip.go` | 标准库 `gzip` | 小 | 低 |
| 压缩：xz | `compress_xz.go` (`ulikunitz/xz`) | `lzma`（标准库含 xz）或 `py7zr` | 小 | 低 |
| 压缩：zstd | `compress_zstd.go` (`klauspost/compress`) | `zstandard` 库 | 小 | 低 |
| 压缩：WebP | `compress_webp.go` (`gen2brain/webp`) | `Pillow`（WebP 支持）或 `pywebp`；需处理 NRGBA 像素矩阵 | 中 | 高 |
| 压缩：ZIP | `compress_unzip.go` + `compress_zipsog.go` | 标准库 `zipfile` | 小 | 低 |
| 文件操作 | `common_file.go` | `pathlib` + `shutil` + `os` | 小 | 低 |
| 版本检查 | HTTP GET + JSON 解析 | `requests` + `json` | 小 | 低 |

**关键挑战：**
- `common.go` 里约 **50+ 个编解码函数**（SPZ/SPX/SOG/Splat 各自的 position/scale/rotation/color 编码），需逐个移植，且要确保精度一致
- WebP 无损编码的像素矩阵拼接逻辑需要用 `numpy` 或 `Pillow` 重写，需特别注意 NRGBA 通道顺序

---

### Phase 2：核心数据结构 — `gsplat/` → `core/`

| 子任务 | Go 来源 | Python 方案 | 工作量 | 难度 |
|--------|---------|-------------|--------|------|
| `SplatData` 结构体 | `data-splat.go` | `dataclass` 或 `numpy` 结构化数组（推荐后者，百万级点性能差距大） | 中 | 高 |
| 四元数 / 向量 | `data-splat.go` Quaternion/Vector3 | 手写或用 `scipy.spatial.transform.Rotation` | 小 | 低 |
| Morton 码排序 | `data-morton.go` | 纯 Python（bit 操作），或用 `numpy` 向量化 | 小 | 中 |
| SH 旋转变换 | `data-roate-sh.go` (3x3/5x5/7x7 矩阵) | `numpy` 矩阵乘法 | 中 | 中 |
| 几何变换（旋转/缩放/平移） | `data-splat.go` TransformDatas | `numpy` 向量化（一次性处理百万点），性能可能优于 Go | 中 | 中 |
| 数据过滤（alpha） | `data-common.go` FilterDatas | `numpy` 布尔索引 | 小 | 低 |
| 包围盒/MinMax | `data-morton.go` | `numpy.min`/`max` | 小 | 低 |

**关键决策：**
> **SplatData 的存储方式决定了整个项目的性能。**
> - 方案 A：Python `dataclass` 列表 — 简单，但百万级点内存和速度差 10-20x
> - 方案 B：NumPy 结构化数组 — `dtype=[('pos', 'f4', 3), ('scale', 'f4', 3), ('color', 'u1', 4), ('rot', 'u1', 4), ('sh', 'u1', 45)]`
> - **强烈推荐方案 B**，所有变换和编解码可完全向量化

---

### Phase 3：格式读写 — 最大的工作量

| 子任务 | 涉及 Go 文件 | Python 方案 | 工作量 | 难度 |
|--------|-------------|-------------|--------|------|
| **PLY 读/写** | `header-ply.go` + `read-gs-ply.go` + `write-gs-ply.go` | `plyfile` 库或手写 `struct.unpack` | 中 | 低 |
| 压缩 PLY 读 | `read-gs-compressed-ply.go` | 手写 chunk 解码 | 中 | 中 |
| **Splat 读/写** | `read-gs-splat.go` + `write-gs-splat.go` | `numpy.fromfile` + `tofile`（最简单） | 小 | 低 |
| **SPX v1/v2/v3 读/写** | 8 个文件 | 手写二进制读写，需处理块分片 + Gzip/XZ/WebP 解压 | 大 | 高 |
| **SPZ v2/v3/v4 读/写** | 5 个文件 | 手写二进制，Gzip/zstd 解压，交错属性数组 | 大 | 高 |
| **SOG v1/v2 读/写** | 5 个文件 | JSON 解析 + WebP 压缩属性文件 + ZIP 打包 | 大 | 高 |
| **KSplat 读** | `read-gs-ksplat.go` | 手写多段二进制解析 | 中 | 中 |
| **GLB 读/写** | `read-glb.go` + `write-glb.go` | `struct` 解析 GLB 头，支持 3 种 glTF 扩展 | 大 | 高 |
| **LOD 系统** | `lod-meta-*.go` 3 个文件 | B-Tree 空间分割 + JSON + 并发文件加载 | 大 | 高 |

**性能关注点：**
- SPX/SPZ 的块读取（逐点解码循环）在 Python 中会极慢 → 必须用 `numpy` 向量化或用 `memoryview`/`mmap`
- GLB 的 JSON chunk 解析可用标准 `json`，但二进制缓冲区需用 `numpy.frombuffer`

---

### Phase 4：高级功能

| 子任务 | Go 来源 | Python 方案 | 工作量 | 难度 | 备注 |
|--------|---------|-------------|--------|------|------|
| K-Means 聚类 | `data-kmeans.go`（422 行，含多线程快速聚类） | `scipy.cluster.vq.kmeans2` 或 `sklearn.cluster.MiniBatchKMeans` | 中 | 中 | Python ML 库天然优势，可能更简单 |
| 模型简化 | `data-simplify.go`（419 行，体素化合并） | 手写体素哈希 + NumPy，或用 `trimesh` 辅助 | 大 | 高 | 算法复杂且含空间哈希，需仔细移植 |
| OBJ 顶点变换 | `data-obj.go` | 文件流逐行处理 + NumPy 旋转 | 小 | 低 | |

---

### Phase 5：CLI 与工程化

| 子任务 | 说明 | 工作量 |
|--------|------|--------|
| CLI 框架 | `click` 或 `typer` 实现 50+ 子命令 | 中 |
| 测试 | 每种格式的读写 round-trip 测试，用标准测试文件对照 Go 版本输出 | 大 |
| 打包发布 | `PyInstaller` 单文件 或 `pip install gsbox` | 中 |
| 性能基准 | 对大文件（>100 万点）做 Go vs Python 性能对比 | 小 |
| 类型提示 | 全项目 `type hints` + `mypy` 检查 | 小 |

---

## 三、推荐的实施顺序

```
Phase 1 (2-3 周)
  └─ common 工具层 + 编解码函数 + 单元测试

Phase 2 (1-2 周)
  └─ SplatData (NumPy 方案) + 几何变换 + Morton 排序

Phase 3 (3-4 周) ← 核心工作量
  ├─ PLY + Splat 读写（最简单，先打通全流程）
  ├─ SPZ 读写（v2 → v3 → v4）
  ├─ SPX 读写（v1 → v2 → v3）
  ├─ SOG 读写 + WebP 压缩
  ├─ KSplat 读取
  └─ GLB 读写（3 种扩展）

Phase 4 (2-3 周)
  ├─ LOD 空间分割构建
  ├─ K-Means 聚类
  ├─ 模型简化
  └─ autocut 全流程

Phase 5 (1-2 周)
  └─ CLI 整合 + 打包 + 基准测试
```

**总估计：9-14 周（单人全职）。**

---

## 四、主要风险与建议

| 风险 | 影响 | 建议 |
|------|------|------|
| **性能不足** | 百万级点的逐点循环解码/编码慢 50-100x | 从第一天起用 NumPy 结构化数组，避免逐点 Python 循环 |
| **精度偏差** | float 编解码在不同语言中可能有微小差异 | 用 Go 版本生成 golden test files，Python 输出做 byte-level 比对 |
| **WebP 兼容性** | Go 用 `gen2brain/webp` 的无损编码，Python Pillow 的 WebP 无损模式可能不完全等价 | 优先验证 WebP 无损 round-trip，如不兼容则使用 `libwebp` C 绑定 |
| **SPX 专有格式** | 块格式复杂（6 种 block format x 多版本），文档有限 | 先确保 v3 + `BF_SPLAT220_WEBP` 这一最常用路径正确 |
| **GLB 扩展** | `KHR_gaussian_splatting` 还是 candidate 状态，规范可能变 | 冻结目标版本，先只支持读不写 |

---

## 五、Python 推荐依赖列表

```
numpy>=1.24
scipy>=1.10
Pillow>=10.0          # WebP 编解码
zstandard>=0.21       # Zstd 压缩
requests>=2.28        # HTTP 下载/版本检查
click>=8.0            # CLI 框架
plyfile>=1.0          # PLY 读写（可选，手写也行）
scikit-learn>=1.3     # K-Means 聚类（可选）
```

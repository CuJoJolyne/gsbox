# gsbox 代码仓库分析报告

## 1. 项目概述

**gsbox** 是一个跨平台的 3D Gaussian Splatting (3DGS) 命令行工具，使用 Go 语言编写（当前版本 `v4.8.4`）。核心功能聚焦于 3D 高斯溅射模型的格式转换、数据优化、空间变换、模型合并和 LOD（层次细节）生成。

### 1.1 支持的格式

| 格式 | 读取 | 写入 | 说明 |
|------|------|------|------|
| `.ply` | ✅ | ✅ | 3DGS 官方 PLY 格式 |
| `.compressed.ply` | ✅ | ❌ | SuperSplat 压缩 PLY 格式 |
| `.splat` | ✅ | ✅ | 简单二进制高斯格式（32字节/点） |
| `.spx` | ✅ | ✅ | 自定义分块压缩格式（支持 WebP 编码） |
| `.spz` | ✅ | ✅ | Niantic 压缩格式（gzip/zstd，v2/v3/v4） |
| `.ksplat` | ✅ | ❌ | GaussianSplats3D 分区块格式 |
| `.sog` | ✅ | ✅ | PlayCanvas 分离文件/ZIP 打包格式 |
| `.glb` | ✅ | ✅ | glTF 二进制格式（`KHR_gaussian_splatting` 扩展） |
| `lod-meta.json` | ✅ | ✅ | LOD 层级流式加载格式 |

### 1.2 依赖库

- `github.com/gen2brain/webp` — WebP 编解码
- `github.com/ulikunitz/xz` — XZ 压缩
- `github.com/klauspost/compress/zstd` — Zstd 压缩
- `golang.org/x/image/webp` — WebP 解码（标准扩展库）

---

## 2. 项目结构

```
gsbox/
├── main.go              # 程序入口，命令路由
├── go.mod / go.sum      # Go 模块依赖
├── README.md            # 使用文档
├── LICENSE              # 开源协议
├── cmn/                 # 通用工具模块
│   ├── version.go       # 版本号定义
│   ├── common.go        # 编解码、数学、字符串、哈希等通用函数
│   ├── common_file.go   # 文件/目录操作
│   ├── os_args.go       # 命令行参数解析器
│   ├── compress_gzip.go # Gzip 压缩/解压
│   ├── compress_xz.go   # XZ 压缩/解压
│   ├── compress_zstd.go # Zstd 压缩/解压
│   ├── compress_webp.go # WebP 编解码（图片方式压缩高斯数据）
│   ├── compress_unzip.go# ZIP 解压
│   └── compress_zipsog.go # SOG 专用 ZIP 打包
└── gsplat/              # 3D 高斯溅射核心模块
    ├── args-common.go   # 命令行参数初始化与参数获取
    ├── exclusive-cmn.go # 生命周期、进度报告、数据处理入口
    ├── data-splat.go    # SplatData 核心结构体及几何变换
    ├── data-common.go   # 输出格式判断、数据过滤
    ├── data-consts.go   # 块格式常量定义
    ├── data-obj.go      # OBJ 顶点转换
    ├── data-sog.go      # SOG/LOD JSON 结构体定义
    ├── data-morton.go   # 空间包围盒和 Morton 码排序
    ├── data-freq.go     # 数据频率统计
    ├── data-kmeans.go   # K-Means 聚类（SH 系数量化）
    ├── data-simplify.go # 高斯简化（体素化合并）
    ├── data-roate-sh.go # 球谐系数旋转变换
    ├── header-ply.go    # PLY 文件头解析
    ├── header-spx.go    # SPX 文件头（128 字节，含哈希校验）
    ├── header-spz.go    # SPZ 文件头（v2/v3/v4 多版本）
    ├── header-sog.go    # SOG 元信息头
    ├── read-gs-ply.go          # PLY 读取
    ├── read-gs-compressed-ply.go # 压缩 PLY 读取
    ├── read-gs-splat.go        # Splat 读取
    ├── read-gs-spx.go          # SPX 读取（版本路由）
    ├── read-gs-spx-v1.go       # SPX v1 读取
    ├── read-gs-spx-v2.go       # SPX v2 读取
    ├── read-gs-spx-v3.go       # SPX v3 读取
    ├── read-gs-spz.go          # SPZ 读取（v2/v3/v4）
    ├── read-gs-sog.go          # SOG 读取（分发）
    ├── read-gs-sog-v1.go       # SOG v1 读取
    ├── read-gs-sog-v2.go       # SOG v2 读取
    ├── read-gs-ksplat.go       # KSplat 读取
    ├── read-glb.go             # GLB 读取（多扩展支持）
    ├── write-gs-ply.go         # PLY 写入
    ├── write-gs-splat.go       # Splat 写入
    ├── write-gs-spx.go         # SPX 写入（版本路由）
    ├── write-gs-spx-v1.go      # SPX v1 写入
    ├── write-gs-spx-v2.go      # SPX v2 写入
    ├── write-gs-spx-v3.go      # SPX v3 写入
    ├── write-gs-spz.go         # SPZ 写入（版本路由）
    ├── write-gs-spz-v2v3.go    # SPZ v2/v3 写入
    ├── write-gs-spz-v4.go      # SPZ v4 写入
    ├── write-gs-sog-v2.go      # SOG v2 写入
    ├── write-glb.go            # GLB 写入（多扩展支持）
    ├── lod-meta-cut.go         # LOD 空间分割构建
    ├── lod-meta-read.go        # LOD 元信息读取
    └── lod-meta-write-sog-v2.go # LOD 元信息写入
```

---

## 3. 模块设计分析

### 3.1 入口层 — `main.go`

**职责：** 程序入口和命令路由。

- 调用 `gsplat.OnMainStart()` 初始化命令行参数，返回 `*cmn.OsArgs`。
- 使用 `if-else if` 链按命令字符串匹配，路由到对应的转换函数（如 `ply2spx()`、`join()`、`cut()` 等）。
- 每个转换函数遵循统一模式：**读入 → 处理 → 写出 → 输出日志**。
- 调用 `gsplat.OnMainEnd()` 完成退出（包含版本检查提示）。
- 支持约 50+ 个转换子命令，涵盖所有格式之间的互相转换。

### 3.2 通用工具模块 — `cmn/`

#### 3.2.1 版本管理 (`version.go`)
- 单文件常量 `VER = "v4.8.4"`，全项目引用。

#### 3.2.2 通用函数库 (`common.go`)
核心能力包括：

| 分类 | 功能 |
|------|------|
| **数值编解码** | float32↔uint16 定点编码、float32↔3字节编码、float16解码、对数编码 |
| **SPZ 专用编码** | 位置(24位定点)、缩放(8位)、旋转(4字节/quaternion 紧凑编码)、颜色、SH系数量化 |
| **Splat 编码** | 缩放(sigmoid)、颜色(SH_DC)、透明度(sigmoid)、旋转、SH系数的编解码 |
| **SPX 专用编码** | 位置(24位定点)、缩放、SH量化、旋转(3字节重建W) |
| **SOG 专用编码** | 旋转(4字节紧凑编码，存储最大分量索引+3个归一化值)、对数缩放 |
| **几何变换** | 度数↔弧度转换、旋转归一化 |
| **数据操作** | 字符串处理、类型转换、范围裁剪、哈希校验 |
| **网络** | HTTP POST/GET、文件下载 |
| **版本检查** | 启动时异步检查远程最新版本 |

关键设计亮点：
- **多版本旋转编码：** 支持 SPZ v2/v3 的简单 3 字节编码和 v3/v4 的 4 字节紧凑四元数编码（存储最大分量索引 + 3 个 10 位量化的其余分量）。
- **SOG 旋转编码：** 使用 RGBA 4 字节存储，alpha 通道存最大分量索引（252+index），RGB 存储其余 3 个分量。
- **对数编码：** 支持多次递归对数编码（`EncodeLog`/`DecodeLog`），用于 SPX 坐标压缩。

#### 3.2.3 文件操作 (`common_file.go`)
- 提供文件存在性检查、读写、复制、目录创建、临时目录管理、后缀文件列表获取等功能。
- 支持网络文件路径判断（`http://` / `https://`）。

#### 3.2.4 命令行解析器 (`os_args.go`)
- 自定义轻量级命令行解析器，支持：
  - 指令（非 `-` 前缀，忽略大小写）
  - 参数名（`-` 前缀）+ 参数值
  - 重复参数名（如多个 `-i` 输入文件）
  - 忽略大小写的参数查找
  - float32 参数值范围校验

#### 3.2.5 压缩模块系列
| 文件 | 能力 |
|------|------|
| `compress_gzip.go` | Gzip 压缩/解压，用于 SPZ v2/v3 |
| `compress_xz.go` | XZ 压缩/解压，SPX 备选压缩方式 |
| `compress_zstd.go` | Zstd 压缩/解压，全局复用线程安全的编解码器 |
| `compress_webp.go` | WebP 无损编解码，将高斯属性当作图片像素压缩 |
| `compress_unzip.go` | ZIP 解压，用于提取 .sog/.ksplat 打包文件 |
| `compress_zipsog.go` | SOG 专用 ZIP 打包，将多个属性文件打包为 `.sog` |

关键亮点：**WebP 图片编码** — 将量化后的高斯属性（如 SH 系数、坐标等）排列成图片像素矩阵，利用 WebP 无损压缩进行二次压缩，显著提升压缩率。

### 3.3 核心高斯模块 — `gsplat/`

#### 3.3.1 核心数据结构 (`data-splat.go`)

```go
type SplatData struct {
    PositionX/Y/Z  float32  // 位置坐标
    ScaleX/Y/Z     float32  // 缩放（log 空间存储）
    ColorR/G/B     uint8    // RGB 颜色（SH DC 分量编码）
    ColorA         uint8    // 透明度（sigmoid 编码）
    RotationW/X/Y/Z uint8   // 四元数旋转（归一化 uint8 编码）
    SH45           []uint8  // 45 个 SH 系数（1/2/3 阶，各 9/24/45 字节）
    IsWaterMark    bool     // 水印标记
    FlagValue      uint16   // 标志位
    PaletteIdx     uint16   // K-Means 调色板索引
    Lod            uint16   // LOD 层级
}
```

**设计思路：** 统一使用中间格式 `SplatData`，所有格式读取后都转为此结构，处理完后再转为目标格式写出。这种"星型拓扑"设计使得 N 种格式只需要 N 个 Reader + N 个 Writer，而非 N×N 转换器。

**几何变换：** 支持 6 种变换顺序（RST/RTS/SRT/STR/TRS/TSR），使用四元数旋转，同时正确变换位置和旋转分量，以及 SH 系数的旋转变换。

**排序策略：**
- `.splat` 输出：按体积/透明度排序（原始 splat 渲染优化）
- 压缩格式输出：按 Morton 码排序（空间局部性，提高压缩率）

#### 3.3.2 命令行参数管理 (`args-common.go`)
- 全局变量 `Args` 和 `oArg` 管理命令行状态
- `ArgValues` 结构封装质量参数（1-9）、K-Means 参数（迭代次数 5-50、近邻数 10-200）、块大小、切割大小等
- **质量级别自动调参：** 根据用户设定的质量等级（默认 5），自动调整 K-Means 迭代次数、近邻数和 WebP 质量参数

#### 3.3.3 生命周期与进度 (`exclusive-cmn.go`)
- `OnMainStart()` / `OnMainEnd()` 管理生命周期
- 后台 goroutine 定时（1秒）输出总进度百分比
- `ProcessDatas()` 统一数据处理管线：过滤 → 变换 → 排序
- 开放版/专版标识管理（CreaterId、ExclusiveId、Hash 校验）

#### 3.3.4 空间计算 (`data-morton.go`)
- `ComputeXyzMinMax()` — 计算包围盒（同时计算中心点和半径）
- `EncodeMorton3()` — 将 3D 坐标编码为 Morton 码（Z-order curve），用于空间局部性排序
- 支持普通坐标和对数坐标两种 MinMax 计算

#### 3.3.5 K-Means 聚类 (`data-kmeans.go`)
- `ReWriteShByKmeans()` — 对球谐系数进行 K-Means 聚类量化
- 支持快速聚类（`tryFastClustering`）和标准 K-Means 两种路径
- 聚类结果生成调色板（centroids）和索引（labels）
- 用于 SOG v2 和 SPZ 的 SH 系数压缩
- 多线程并行实现（`runtime.NumCPU()` + `sync`）

#### 3.3.6 模型简化 (`data-simplify.go`)
- `Simplify()` — 基于体素化的贪婪高斯合并算法
- 网格大小由平均缩放系数驱动（`gridSizeFactor = 2.5`）
- 使用空间哈希（`flatHash`）进行近邻查找
- 合并条件：尺度比、透明度、空间距离等
- 多线程并行，按块（blockSize=128）处理

#### 3.3.7 球谐旋转 (`data-roate-sh.go`)
- `SHRotation` 结构存储 1/2/3 阶 SH 旋转矩阵
- 从四元数构建旋转矩阵，分别生成 3×3、5×5、7×7 的 SH 变换矩阵
- 移植自 PlayCanvas SuperSplat 项目的 `sh-utils.ts`

#### 3.3.8 频率统计 (`data-freq.go`)
- `FrequencyCounter` 用于统计缩放、颜色、旋转值的出现频率
- 辅助分析数据冗余度，为压缩策略提供参考

### 3.4 格式读写实现

#### 3.4.1 PLY 读写
- **读取：** 解析 ASCII 头部（属性名→偏移→类型映射），支持标准 3DGS PLY、SuperSplat 压缩 PLY（chunk-based quantization）、RGB 点云 PLY
- **压缩 PLY 特殊处理：** 每 256 个顶点一个 chunk，存储 18 组 min/max 边界值，顶点数据以 16 字节量化记录存储
- **写入：** 生成标准 binary_little_endian PLY，支持自定义 comment 和 SH 阶数控制

#### 3.4.2 Splat 读写
- **最简单的格式：** 每个高斯点固定 32 字节（12B 位置 + 12B 缩放 + 4B 颜色 + 4B 旋转）
- 读取时使用 2MB 缓冲区批量读取 4096 个点
- 写入时直接序列化编码值

#### 3.4.3 SPX 读写（v1/v2/v3）
- **自定义分块格式：** 128 字节头部 + 多个数据块
- **块格式：** 支持多种编码方式：
  - `BF_SPLAT22/23` — 每点 20/22 字节直接编码
  - `BF_SPLAT220/230_WEBP` — 编码后拆分通道再 WebP 压缩
  - `BF_SH_PALETTES` — K-Means 调色板量化 SH
- **v2 增加：** 标志位（IsInverted、IsLargeScene）
- **v3 增加：** LOD 层级、调色板数据
- **坐标编码：** 支持 24 位定点编码和对数编码两种模式
- **头哈希校验：** 前 124 字节计算哈希存入尾部 4 字节

#### 3.4.4 SPZ 读写（v2/v3/v4）
- **v2/v3：** Gzip 压缩，交错属性数组（位置→alpha→颜色→缩放→旋转），旋转存储 3 字节（v3）或 4 字节（v2，兼容旧格式）
- **v4：** 新格式，32 字节头部，支持 NumStreams 和 TocByteOffset，结构更灵活
- 位置使用 24 位定点编码（FractionalBits=12）

#### 3.4.5 SOG 读写
- **v1：** 直接二进制属性文件 + `meta.json` 清单
- **v2：** 增强格式，增加 WebP 压缩、K-Means SH 量化、分文件存储
- **打包格式：** 属性文件可打包为 `.sog`（ZIP 格式），或以 `meta.json` + 散文件形式存在
- 支持 HTTP URL 远程读取（自动下载到临时目录）

#### 3.4.6 KSplat 读取
- 多段（Section）结构，每段 1024 字节头 + 空间分桶数据
- 支持 3 种压缩模式（无压缩/量化 1/量化 2）
- SH 值限制在 [-1.5, 1.5] 范围内

#### 3.4.7 GLB 读写
- 基于 glTF 二进制格式，支持 3 种扩展：
  1. `KHR_gaussian_splatting` — 标准属性缓冲区（candidate extension）
  2. `KHR_gaussian_splatting_compression_spz_2` — 内嵌 SPZ 压缩数据
  3. `com_github_gotoeasy_gsbox_webp_rgb_ply` — WebP 压缩 RGB 点云
- GLB JSON 头对齐到 4 字节边界

### 3.5 LOD 系统

#### 3.5.1 LOD 空间分割 (`lod-meta-cut.go`)
- `BuildLodMetaSplatTiles()` — 使用 B-Tree 空间分割构建 LOD 层次树
- `SplatNode` 递归树节点，存储中心点、半径、AABB 包围盒
- 叶子节点产生文件输出，内部节点定义 LOD 层级关系
- 文件阈值 `FileSplatCountThreshold = 409600`，超大文件自动分段

#### 3.5.2 LOD 读取 (`lod-meta-read.go`)
- 解析 `lod-meta.json`，遍历 LOD 树分配层级
- 多线程并发加载所有引用的 SOG 数据文件
- 分离环境数据和主体 LOD 数据

#### 3.5.3 LOD 写入 (`lod-meta-write-sog-v2.go`)
- 按 LOD 层级和序号排序后遍历写入
- 每个 tile 独立写为 SOG v2 格式（支持 WebP + K-Means 压缩）
- 可选输出环境模型 `environment.sog`
- 最终生成 `lod-meta.json` 清单文件

### 3.6 `autocut` 功能
- **自动多层次简化：** 从原始模型开始，连续调用 `Simplify()` 生成 6 个 LOD 级别（LOD 0-5）
- 每一级在前一级基础上进一步简化，输出简化率日志
- 将所有 LOD 层级数据合并且进行 B-Tree 空间分割
- 最终输出完整的 `lod-meta.json` + 分块 SOG 文件

---

## 4. 核心设计模式

### 4.1 星型转换拓扑
所有格式读取后统一转为 `[]*SplatData`，处理完后再转为目标格式。N 种格式只需 N 个 Reader + N 个 Writer，避免 N×N 组合。

### 4.2 数据处理管线
```
读取(Read) → Alpha过滤(Filter) → 几何变换(Transform) → 排序(Sort) → 写出(Write)
                                     ↓
                    旋转(Rotate) → 缩放(Scale) → 平移(Translate)
                         ↓
                    SH球谐旋转(SHRotation)
```

### 4.3 多版本兼容
SPX 和 SPZ 格式都支持多版本（v1/v2/v3 和 v2/v3/v4），使用头部版本号路由到对应的读写实现。

### 4.4 质量参数驱动
质量等级（1-9）自动驱动：
- K-Means 聚类迭代次数和近邻数
- WebP 编码质量（80-99）
- SH 系数量化精度

### 4.5 空间优化排序
压缩格式输出前使用 Morton 码排序，提升空间局部性以增强 gzip/zstd/WebP 压缩效果。

### 4.6 并发设计
- K-Means 聚类：多线程并行计算距离和更新聚类中心
- LOD 读取：`sync.WaitGroup` 并发加载多个数据文件
- SOG 读取：并发加载属性文件（means/scales/quats/sh0/shN）
- 模型简化：按块并行处理

---

## 5. 关键编码/压缩策略

| 属性 | 编码方式 | 字节数 |
|------|----------|--------|
| 位置 (SPX/SPZ) | 24位定点 (fractionalBits=12) | 3 |
| 缩放 (SPX/SPZ) | 8位线性 ((val+10)×16) | 1 per axis |
| 透明度 | sigmoid 编码 uint8 | 1 |
| 颜色 (DC) | SH_C0 编码 uint8 | 1 per channel |
| 旋转 (splat) | 线性 uint8 ((val+1)×128) | 1 per component |
| 旋转 (SPX) | 丢弃 W 分量，3 字节重建 | 3 |
| 旋转 (SPZ v3/v4) | 4字节紧凑四元数 (2+10+10+10 bit) | 4 |
| 旋转 (SOG) | RGBA 4字节 (最大分量索引+3值) | 4 |
| SH 系数 (K-Means) | 聚类量化+调色板索引 | 1-2 per coeff |
| 坐标 (SPX log) | 多次递归对数编码 + 24位定点 | 3 |
| WebP 二次压缩 | 属性→像素矩阵→WebP 无损编码 | 可变 |

---

## 6. 文件统计

| 模块 | 文件数 | 代码行数（约） |
|------|--------|----------------|
| 根目录 | 4 | ~1300 |
| `cmn/` | 12 | ~2000 |
| `gsplat/` | 43 | ~12000+ |
| **合计** | **59** | **~15000+** |

---

## 7. 总结

gsbox 是一个功能完备的 3DGS 格式转换工具，具有以下特点：

1. **统一的中间表示（`SplatData`）** 实现了格式间的灵活转换
2. **多层次压缩策略**：数值量化 → 空间排序 → 块压缩 → WebP 图片编码
3. **多版本格式兼容**：SPX(v1-v3)、SPZ(v2-v4)、SOG(v1-v2) 均支持读写
4. **完整的 LOD 系统**：自动简化 + B-Tree 空间分割 + 分块流式加载
5. **纯 Go 实现**，跨平台无 CGO 依赖（WebP 通过 purego/wazero 实现）
6. **高质量的几何变换**：正确处理位置、旋转、SH 系数的联合变换

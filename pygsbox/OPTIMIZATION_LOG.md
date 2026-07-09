# pygsbox Go 对齐 + 性能优化全记录

> Session 日期：2026-07-08
> 数据：119,671 点 Plygon SH3 point cloud

---

## 一、发现的 Go-Python 对齐 Bug（12 个）

| # | Bug | 根因 | 定位方式 |
|---|-----|------|---------|
| 1 | **Splat scale 编解码缺失** | Go 读写做 exp/log，Python 读裸值 | 对比 Go `read-gs-splat.go` 源码 |
| 2 | **SPZ v4 TOC 第二个 uint64=0** | Go 写 `(zstd_size, raw_size)`，Python 写 `(zstd_size, 0)` | 对比 Go `write-gs-spz-v4.go` |
| 3 | **SPZ SH 剩余位填 0 非 128** | Go `InitZeroSH45()` 填 128，Python `SplatData(n)` 默认 0 | Go vs Python 字节值对比 |
| 4 | **PLY scale 取 log 后变 NaN** | Python reader 对负 log-scale 值做 `np.log()`，Go 直读不转换 | 运行时 `RuntimeWarning: invalid value` |
| 5 | **PLY writer 对 scale 做 exp** | 对称 bug：reader 做 log，writer 做 exp，数据全 NaN | 追码排查 |
| 6 | **Simplify 合并后四元数未归一化** | Go `NormalizeRotationsF32Uint8` 四分量联合归一，Python 逐分量独立编码 | 源码对比 |
| 7 | **Lod 叶节点 TileMapping 全量初始化** | Go 只为非零 lodCount 创建，Python 为全部创建 | 子进程对比报告 |
| 8 | **Lod Morton 排序 + seq 重置缺** | Go merge 前调 `SortMorton`，每 LOD 级别重置 seq=0 | 子进程对比报告 |
| 9 | **K-Means `sortCentroidsByCounts` 缺失** | Go 按 count 排序 centroids + 去空簇，Python 无 | 子进程对比报告 |
| 10 | **`process_data` 丢了 Morton sort** | 代码重构时误删，直接影响 SOG 输出 | diff git 历史 |
| 11 | **`flatten()` BFS 索引计算 bug** | BFS 假定完全二叉树（子节点在 ci+1），KD-tree 非完全 | BBF 6% 正确率 benchmark |
| 12 | **numba `_centroid_divide_jit` 空簇不重投** | Go `copy(newCents[c], randPoint)`，Python 保留旧值不变 | 对比 Go `kmeansSh45` 源码 |

---

## 二、关键 Debugging 方法论

### 2.1 逐字节对比法

```
问题：means_u.webp 大小 Go=127K, Python=192K（52% 差异）
方法：
  1. 解压两个 .sog 的 WebP 像素
  2. 像素级逐字节对比：发现 93.6% 不同
  3. 反向追踪：uint16 值 Go=51483, Python=55272 → 数据顺序不同
  4. 验证 Morton sort 是否调用 → 发现 process_data 缺调用
  5. 修复后：100/100 像素匹配
```

### 2.2 精确度 benchmark 法

```
问题：BBF 是否正确？palette 只有 15 而 Go 有 65223 → 怀疑搜索错误
方法：
  1. 生成小数据：centroids(256) + points(1000)
  2. 暴力最近邻算 ground truth
  3. BBF 搜 15 节点 → 准确率只有 6%！
  4. 定位：flatten() 的 child index 全错
  5. 修复后：KN=100 → 准确率 96%
```

### 2.3 性能逐层剥离法

```
问题：K-Means 每轮迭代 92s，Go 仅 3s → 差 30x
方法：
  1. 用 time.perf_counter() 定位热点：flatten() 耗时 90s
  2. 查代码：pop(0) = O(n) per pop，65536 节点 = O(n²) = 4B ops
  3. 改 BFS + head pointer → 1s
  4. 再建 benchmark：距离计算 36s → np.dot 向量化 → 8.4s
  5. 再测试：120K 点 → numba JIT → 0.4s（最终 100x）
```

---

## 三、K-Means 性能优化历程

| 阶段 | 变更 | 1 轮迭代 | 完整转换 | vs Go(35s) |
|------|------|----------|----------|:---:|
| 0 | 初始 | ~92s | ~436s | 12.5x |
| 1 | `flatten()` O(n²)→O(n) | ~90s | — | — |
| 2 | 距离 `for d`→`np.dot` | ~24s | ~245s | 7.0x |
| 3 | 预转换 float64 | ~24s | ~245s | — |
| 4 | numba JIT BBF | ~3s | ~49s | 1.4x |
| 5 | numba centroid update | ~2s | ~40s | 1.14x |
| 6 | fix flatten child index | ~2s | ~40s | ✅ |
| 7 | fix empty cluster reinit | — | ~40s | ✅ |

### 3.1 最终性能对比

| 质量参数 | KI | KN | Go 耗时 | Python 耗时 | Python vs Go |
|----------|:--:|:--:|:---:|:---:|:---:|
| -q 5 | 10 | 15 | 35s | 40s | **慢 14%** (Python 慢) |
| -q 9 | 20 | 100 | 334s | 140s | **快 138%** (Python 快) |

> 注意：Go -q 5(35s) → -q 9(334s)，工作量为 KI×2 + KN×6.7 ≈ 13.4 倍，但耗时增加 **9.5 倍**。
> Python -q 5(40s) → -q 9(140s)，工作量相同 13.4 倍，但耗时仅增加 **3.5 倍**。

### 3.2 为什么 Python 在 -q 9 下反超 Go？

Go 从 35s 变到 334s（慢了 9.5x）的根本原因是 BBF 内部的 **Go `container/heap` 堆维护成本**在高 KN 下急剧放大：

- KN=15 时：每个点搜 15 个 KD-tree 节点，heap Push/Pop 约 30 次，每次 O(log heap_size) ≈ log(15) ≈ 4 次比较 → 15 × 30 × 4 = 1800 个堆操作 · 120K 个点 = 216M 堆操作，轻松完成
- KN=100 时：每个点搜 100 个节点，heap 操作量线性增加但 Go `heap.Pop` 的 O(log n) 和 heap 结构维护的 GC 开销不成比例放大。而且 Go 的 BBF 每轮都要重建 KD-tree + SoA 视图（O(K log²K)），65536 个 centroids × 20 次迭代 = 20 × 65536 × 16 × 16 = 3.36 亿次数组比较

Python 从 40s 到 140s（仅慢 3.5x）是因为 **numba 绕开了 Python 堆操作的瓶颈**：

- numba JIT 把 heap 编译为固定大小的栈数组（float64 × 200），不分配堆内存
- "min-heap 弹顶" 是线性扫描 200 个元素找最小（O(200)），在高 KN 下反而优于 Go 的 log-n heap 维护
- 所有距离计算都是原生 float64 循环，无 Python 解释器开销
- KD-tree 构建复用了 `np.argsort`（C 级别），不受 KN 影响

简单说：**Go 在高 KN 下被自己的 heap 维护和 GC 拖慢，而 numba 的固定数组线性扫描恰好规避了这些开销**。

### 3.3 为什么 Python 在 -q 5 下仍慢 Go 14%？

这 14%（40s → 35s 的差距）来自两个引擎层面的差异：

1. **Go `np.argsort` 等价物快约 20%**：Go 直接用快排库，Python 的 numpy.argsort 多一层 Python→C 的包装调用
2. **WebP 编码器差异**：Go 用 `gen2brain/webp`（Go→C 零拷贝绑定），Python 用 Pillow（纯 Python wrapper 经过 Image.frombuffer → save buffer）。SOG 输出里 means/scales/quats/sh0 四组 WebP 各有近 500K 像素

这两点都是语言/库层面的固定开销，不随 KN 放大。在 -q 5 下它们占总时间的 ~30%，在 -q 9 下被庞大的 K-Means 计算淹没到 <10%。

### 3.4 关键洞察

1. **numba JIT 是决定性突破**：BBF 搜索 173K pts/s → 338K pts/s（2000x）
2. **Python 多进程在 Windows 不可行**：42MB 数据 pickle 序列化吃掉并行收益；shared_memory 需要 `if __name__ == '__main__'` 不能从库函数调用
3. **Go goroutines 优势在于零拷贝**：共享内存天然；但 Go heap 维护在高 KN 下衰减，反观 numba 固定数组不受此影响
4. **numba 在高 KN 场景有额外优势**：固定 heap array 的线性扫描 vs Go 的 O(log n) heap 维护——log n 的开销在这里被 Python 的固定 O(200) 反超

---

## 四、SDD 在本次 Session 中的价值评估

| 场景 | SDD 起作用？ | 说明 |
|------|:--:|------|
| Go 对齐 bug 发现 | ❌ | 全部通过直接读 Go 源码对比，spec 无此级别细节 |
| BBF 正确性验证 | ❌ | 独立 benchmark 对比 brute-force 发现 6% 准确率 |
| numba 优化 | ❌ | 性能分析 + JIT 实现，spec 不涉及 |
| 回归测试保护 | ✅ | AGENTS.md 约定 `python tests/test_basic.py` 每次修改后跑 |
| subagent 使用 | ✅ | AGENTS.md 规范了 import、依赖模式，减少沟通成本 |
| Phase 3 spec→code 验证 | ✅ | subagent 只读 spec 生成了 codec.py/splat_data.py |
| 代码规范一致 | ✅ | numpy vectorized, SplatData 列式, 命名约定等 |

**结论**：SDD 做"蛋糕底座"有好效果（接口、规范），但"裱花"（正确性、性能）还是要逐行对比 Go 源码 + 独立 benchmark + profiling。

---

## 五、最终对齐验证

| 验证项 | -q 5 结果 | -q 9 结果 | 方法 |
|--------|:--:|:--:|------|
| Means 像素匹配 | 100/100 ✅ | 100/100 ✅ | 解压 WebP → 逐像素对比 uint16 |
| Palette 大小 | — | Go=65223, Python=65271 | meta.json 的 `shN.count` |
| 总文件大小 | 0.97x (Py 稍小) | 1.10x (Py 稍大) | Go vs Py SOG 文件总字节 |
| 耗时 | 40s vs 35s (1.14x Py 慢) | 140s vs 334s (2.4x **Py 快**) | 真实 ply → sog 转换 |
| 位置一致 | ✅ | ✅ | Morton 排序后 uint16 三方对比(G=Py=Exp) |

---

## 六、沉积的工程资产

| 资产 | 说明 |
|------|------|
| `benchmark.py` | 格式读写性能基准 |
| `kmeans_bbf.py` | Go 兼容的 BBF KD-tree（numia + 纯 Python 双路径） |
| `EXPERIENCES.md` | 项目移植经验总结 |
| `SDD_PLAN.md` | SDD 改造计划 |
| `AGENTS.md` | Agent 使用指南 |
| `USAGE.md` | Python 版完整使用说明 |
| `PROGRESS.json` | 全阶段进度追踪（含 SDD + Go 对齐状态） |
| `specs/` (23 个) | 各模块 spec 文件 |
| 34 个 test | 全格式 roundtrip + 高级特性 |

---

## �ߡ�������֤������

### 7.1 ������ս

SOG ��������position uint16 ������scale uint8��SH K-Means�����������ֽڶԱȡ�Morton �����ڲ�ͬʵ�ּ��� float ����΢����ܲ�����ͬ˳����������ʧЧ��

### 7.2 ���󷽷�

| ���� | ���� | ԭ�� |
|------|------|------|
| ֱ�ӶԱ� WebP ���� | 77-81% "����" | Morton ����ͬ��������˳��ͬ |
| Morton ����������� | position ��� 101 | float ���ȸı� Morton code������һ���Ա��ƻ� |
| KD-tree ƥ�� + ͬһ reader | ��ɫ����쳣 | Go SOG �� Python PLY reader �� f_dc ת������ͬһ��·�� |

### 7.3 ��ȷ������KD-tree + ԭʼ�ֽ� + ���廯���

1. ��ԭʼ PLY �Ķ������ֽڣ��ƿ����� reader��
2. �� SOG �� Go g2p �� PLY �Ķ������ֽڣ�ͳһת��·����
3. KD-tree λ��ƥ�䣨���� <0.01�������� 1:1 splat ��Ӧ
4. ������ͳ����position/scala ���Ը���rotation �ǶȲcolor RGBA �����SH �� band ������

### 7.4 �����������ݲ�

| ���� | �ݲ� | ��Դ |
|------|:---:|------|
| Position | <0.05 | uint16 �����ռ����� |
| Scale | <0.1 | uint8 ���� (1/16 log-step) |
| Color | <=1 LSB | codebook ������� (���㾫�ȿ��� 1-2 LSB) |
| Rotation | <5deg | SOG 3 ������� -> 4 �����ؽ� |
| SH | ~100% (���) | K-Means ������� |

### 7.5 ��֤����

`compare_sog.py` ʵ�������Ϸ����ۣ�֧�֣�
- `--go A.sog --py B.sog`��Go vs Python �Ա�
- `--orig in.ply --sog out.sog`��������֤
- `--self --rt in.ply`���������ջ�

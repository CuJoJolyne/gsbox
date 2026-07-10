# SDD 实践方法论

> 从 pygsbox SDD 改造中提炼的实践经验（2026-07）

## 核心理念

**SDD 是开发时的脚手架，不是质量保证框架。**

SDD 适合规范**接口层**（字段类型、字节偏移、边界情况），确保 subagent 不写坏架构。但它不能保证算法精度、性能、跨实现等价性——这些靠 benchmark 和 byte-level 验证。

---

## Spec 颗粒度原则

**一个 spec = 一个模块/一个 .py 文件**

| 颗粒度 | 行数 | subagent 能处理？ |
|------|------|:---:|
| 整个系统 | >500 行 | ❌（subagent 会漏掉细节）|
| 模块级 | 50-200 行 | ✅（合理范围）|
| 函数级 | 10-50 行 | ✅（更精细但可能冗余）|
| 单行 spec | <10 行 | ❌（subagent 会臆断）|

**判断标准**：
- spec <50 行 → 太薄，subagent 臆断写出错误实现
- spec >300 行 → 太厚，subagent 漏掉细节
- **50-200 行合理区域**：足够精确又不臃肿

---

## 分工原则

### 1. 开发者写什么

**spec 的结构 + Example 段**

- 字段名、类型、字节偏移、边界情况
- Example 段的**真实值**和**预期行为**
- 这些是 subagent 能准确解读的层次

**为什么开发者必须写 Example？**
- spec 的 Example 来自开发者对系统的真实理解
- 如果让 code agent 写，它会随便猜值（比如颜色范围猜 0-255 而实际是 SH 系数空间值 0-1.4）
- 结果就是 spec 和实际行为对不上，生成的代码带 bug

### 2. Code agent 写什么

**实现代码 + spec 的结构骨架**

- 代码会根据 spec 迭代自动更新
- subagent 不需要审阅每一行实现代码
- 跑测试就知道正确性
- spec 的结构骨架（段落组织、段落命名）可以由开发者起草后 agent 细化

### 3. 测试

**spec 的 Example 段就是测试**

- spec 的 Example 自动生成对应的 test case
- spec 改 Example → 测试同步更新
- 不是另外维护的 test_basic.py 那样的独立文件

---

## 不应该写 spec 的场景

| 场景 | 为什么不写 spec |
|------|----------------|
| **跨实现对齐 bug** | 12 个 bug 全部通过逐行读 Go 源码发现，浮点精度级别的 bug spec 描述不了 |
| **算法正确性验证** | BBF 正确性靠独立 benchmark（23 spots → 6% 正确率 → 发现 bug） |
| **性能优化** | numba JIT 是 profiling 驱动的，spec 不讨论性能 |
| **定量验证** | KD-tree + 语义化误差是方法论演进，spec 无法预判 |

**本质**：这些场景需要**直接读源码 + 独立验证 + benchmark 分析**，不是 spec 能描述的层次。

---

## 决策树

```
要写新模块吗？
  ├─ YES → 有明确 I/O + 无算法复杂度？
  │      └─ YES → 写 100 行 spec + subagent 写代码
  │      └─ NO（有算法复杂度，如 K-Means、LOD）？
  │              └─ 写 spec + 独立写代码 + 独立验证 + 更新 spec
  │
  └─ NO（不是新模块，而是修 bug / 优化性能）？
          └─ 不写 spec，直接读源码 + byte-level 验证
```

---

## 关键认知

1. **Spec ≠ 需求文档**
   - 是精准到可以生成代码的指令，不是高层需求描述
   - 每个字段类型、字节偏移、边界情况都要明确

2. **80% 生成 + 20% 人工**
   - 核心逻辑可从 spec 完全生成（编解码、数据结构）
   - 胶水代码仍需人工（CLI 调度、文件 IO）

3. **Spec 的维护就是开发工作**
   - 不是"先写 spec 再写代码"，"写 spec 就是开发"
   - spec 是交付物，代码是产物

4. **面向 Agent 设计**
   - 目录结构、命名约定、注释风格让 Agent 能"一眼看懂"
   - 这是 SDD 的工程纪律

5. **测试 = Spec 的 Example 段**
   - 不单独维护测试文件
   - 每次改 spec 的 Example，Agent 同步更新测试

---

## Spec 结构模板

每个 spec 包含以下固定结构：

```markdown
# [模块名] Specification

## Purpose（用途）
一句话描述这个模块做什么

## Inputs / Outputs
字段名 | 类型 | 字节偏移 | 边界情况
------|------|--------|--------
x | float32 | 0 | [-1e6, 1e6]
y | float32 | 4 | [-1e6, 1e6]
...

## Boundaries
- 空输入 → 返回零元组
- NaN 输入 → 抛出 ValueError
- 超过范围 → clip 到边界

## Example
Input: x=1.0, y=2.0, z=3.0
Output: x_encoded=1024, y_encoded=2048, z_encoded=3072
Expected behavior: encoded values in [0, 2^16)
```

---

## 何时用 subagent

| 场景 | subagent 能处理？ |
|------|:---:|
| 根据 spec 写纯逻辑模块 | ✅ |
| 根据 spec Example 生成测试 | ✅ |
| 跨实现对齐修 bug | ❌ |
| 性能优化 | ❌ |
| 输出正确性验证 | ❌ |
| 根据 spec 写完整系统 | ❌（太复杂）|

---

## 实用经验

- 写新模块时先写 spec（~30 行 spec + subagent 写代码）→ 有效
- 修对齐 bug / 优化性能 → 直接读源码 + benchmark，更省事
- Spec 写到 100 行精确到字节偏移后，迭代 spec 不再带来额外正确性
- SDD 是防止 subagent 写坏架构和接口的工程纪律
- SDD 不是质量保证，质量保证靠 benchmark + byte-level 验证

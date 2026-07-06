# {模块名} — Specification

> Auto-generated code target: `{path}/{module}.py`

## 1. Purpose

{一句话描述这个模块解决了什么问题}

## 2. Data Structures

{定义所有输入/输出类型，精确到字段类型、约束、单位、shape}

### 2.1 Input Types

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| ... | ... | ... | ... |

### 2.2 Output Types

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| ... | ... | ... | ... |

### 2.3 Constants

| 名称 | 值 | 说明 |
|------|----|------|
| ... | ... | ... |

## 3. Public API

{列出所有公开函数。每个函数需包含：签名、描述、前置条件、后置条件、副作用、错误情况}

### 3.1 `function_name`

- **Signature**: `def fn(a: int, b: str) -> bool`
- **Description**: {做什么}
- **Preconditions**: {调用前必须满足的条件}
- **Postconditions**: {调用后保证成立的条件}
- **Side Effects**: {I/O、全局状态等，若无则写 None}
- **Error Cases**:
  - `ValueError` when {条件}
  - `ImportError` when {可选依赖缺失}

## 4. Algorithm

{如果模块包含复杂算法，描述步骤、关键参数、时间复杂度}

### 4.1 Main Flow

```
1. step one
2. step two
   a. sub-step
   b. sub-step
3. return result
```

### 4.2 Key Parameters

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| ... | ... | ... | ... |

## 5. Edge Cases

| 场景 | 输入 | 期望行为 |
|------|------|---------|
| 空数据 | N=0 | {描述} |
| 无效 magic | magic != expected | 抛出 `ValueError("Invalid magic: {got}")` |
| 数据截断 | len(data) < expected | 抛出 `ValueError("Truncated data")` |
| {其他边界} | ... | ... |

## 6. Examples

{至少包含一个最小完整示例和一个 roundtrip 示例}

### 6.1 Minimal Input

```python
# 最小的可用输入
data = ...
result = module.fn(data)
assert result == expected
```

### 6.2 Roundtrip Test

```python
# write → read → compare
original = gen_data(N=100, seed=42)
module.write(tmpfile, original)
_, decoded = module.read(tmpfile)
assert np.max(np.abs(original.position - decoded.position)) < {tolerance}
```

### 6.3 Edge Case Test

```python
# 边界行为验证
# {描述边界场景}
```

## 7. Dependencies

| 模块 | 用途 |
|------|------|
| {path.module} | {说明} |

## 8. Agent Notes

{给 Code Agent 的特殊提示}

- **命名约定**: {如有}
- **需手写的部分**: {如有}
- **生成时注意**: {陷阱、常见错误}
- **性能要求**: {如有——如必须用 numpy 向量化，禁止逐点循环}
- **可选依赖处理**: {如何处理 try/except ImportError}

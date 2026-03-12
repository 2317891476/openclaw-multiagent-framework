# Testing Guide

> 框架的测试架构遵循分层原则：每一层独立验证。

---

## 测试架构

```
┌──────────────────────────────────────────────────────────┐
│              Completion Relay Tests                       │
│   test_completion_listener.py — 完成通知解析和处理         │
│   task-log 读写 · 消息解析 · JSON/dict/嵌入式格式          │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│              L2 Capability Tests                          │
│       test_l2_capabilities.py — 增强能力验证               │
│  ACK · Handoff · Deliverable · Writer · Bridge · Reflect  │
└──────────────────────────────────────────────────────────┘
```

### 设计理念

1. **Completion Relay 测试**：验证 task-log 的读写、完成消息的解析（JSON 字符串、dict 对象、嵌入文本中的 JSON）、边界条件（空消息、非完成消息、畸形 JSON）。
2. **L2 能力测试**：验证各增强能力的独立逻辑。

---

## 运行测试

### 全部测试

```bash
cd examples
python3 -m pytest completion-relay/tests/ tests/ -v
```

### 单个文件

```bash
# Completion relay
python3 -m pytest completion-relay/tests/test_completion_listener.py -v

# L2 capabilities
python3 -m pytest tests/test_l2_capabilities.py -v
```

### 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_completion_listener.py` | 15 | task-log CRUD、消息解析、边界条件 |
| `test_l2_capabilities.py` | 35 | ACK、Handoff、交付物、单写入者、Bridge、反思 |
| **合计** | **50** | — |

---

## 添加新测试

新测试放在对应 `tests/` 目录下：
- Plugin 相关: `examples/completion-relay/tests/`
- L2 能力相关: `examples/tests/`

遵循 `test_<模块名>.py` 命名约定。

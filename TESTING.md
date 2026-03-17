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

┌──────────────────────────────────────────────────────────┐
│          Subagent Claude Runner Smoke Tests               │
│   test_watchdog_smoke.sh — runner/watcher watchdog smoke  │
│   quiet file activity · hard stall · timeout semantics    │
└──────────────────────────────────────────────────────────┘
```

### 设计理念

1. **Completion Relay 测试**：验证 task-log 的读写、完成消息的解析（JSON 字符串、dict 对象、嵌入文本中的 JSON）、边界条件（空消息、非完成消息、畸形 JSON）。
2. **L2 能力测试**：验证各增强能力的独立逻辑。
3. **Subagent Runner Smoke**：验证本地 CLI runner 的超时、stall 恢复、watcher 事件流和终态摘要。

---

## 运行测试

### 全部测试

```bash
cd examples
python3 -m pytest completion-relay/tests/ tests/ -v
bash subagent-claude-runner/test_watchdog_smoke.sh
```

### 单个文件 / 单组测试

```bash
# Completion relay
python3 -m pytest completion-relay/tests/test_completion_listener.py -v

# L2 capabilities
python3 -m pytest tests/test_l2_capabilities.py -v

# Subagent runner smoke
bash subagent-claude-runner/test_watchdog_smoke.sh
```

### 测试覆盖

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_completion_listener.py` | 15 | task-log CRUD、消息解析、边界条件 |
| `test_l2_capabilities.py` | 35 | ACK、Handoff、交付物、单写入者、Bridge、反思 |
| `subagent-claude-runner/test_watchdog_smoke.sh` | 2 smoke cases | 安静但持续写文件 / 真正卡死 stall timeout |
| **合计** | **52+smoke** | — |

---

## 添加新测试

新测试放在对应 `tests/` 目录下：
- Plugin 相关: `examples/completion-relay/tests/`
- L2 能力相关: `examples/tests/`
- Runner/Watcher smoke: `examples/subagent-claude-runner/`

遵循现有命名约定：
- Python: `test_<module>.py`
- Shell smoke: `test_<name>.sh`

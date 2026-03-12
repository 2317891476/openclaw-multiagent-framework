# Examples

Runnable protocol implementations and utility demos.  
可运行的协议实现和工具示例。

## Core Examples / 核心示例

### completion-relay/ (Recommended / 推荐)

Monitors `task-log.jsonl` for task completion events and dispatches alerts. Works with the `spawn-interceptor` plugin — the plugin writes events, the listener reads them.

监控 `task-log.jsonl` 中的任务完成事件并发出告警。与 `spawn-interceptor` 插件配合使用——插件写入事件，监听器读取。

```bash
# Single check / 单次检查
python3 completion-relay/completion_listener.py --once

# Continuous / 持续监听
python3 completion-relay/completion_listener.py --loop --interval 60
```

15 unit tests / 15 个单元测试: `python3 -m pytest completion-relay/tests/ -v`

### l2_capabilities.py

6 L2 capability demos: ACK protocol, Handoff template, Deliverable layers, Single-writer rule, Follow-up bridge, Daily reflection pipeline.

6 个 L2 增强能力演示：ACK 协议、Handoff 模板、交付物分层、单写入者规则、Follow-up 桥接、每日反思管线。

```bash
python3 l2_capabilities.py
```

35 unit tests / 35 个单元测试: `python3 -m pytest tests/test_l2_capabilities.py -v`

### protocol_messages.py

Protocol message format (request/ack/final) construction and parsing demo, corresponding to AGENT_PROTOCOL.md.

协议消息格式（request/ack/final）的构造和解析演示，对应 AGENT_PROTOCOL.md 规范。

```bash
python3 protocol_messages.py
```

## Deprecated / 已废弃

The following examples were removed in v2 / 以下示例已在 v2 中移除：

| Example | Removal Reason | Replacement |
|---------|---------------|-------------|
| mini-watcher/ | File-polling anti-pattern | completion-relay/ + spawn-interceptor plugin |
| task_state_machine.py | Based on old watcher state machine | spawn-interceptor auto-tracking |
| test-protocol.sh | Outdated test script | completion-relay/tests/ |

See [COMMUNICATION_ISSUES.md](../COMMUNICATION_ISSUES.md) for why we migrated from file-polling to plugin hooks.

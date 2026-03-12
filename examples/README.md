# Examples

可运行的协议实现和工具示例。

## 核心示例

### completion-relay/ (推荐)

ACP 完成通知监听器。配合 `spawn-interceptor` plugin 使用，监听 ACP 子 Agent 的完成回调并转发通知。

```bash
# 单次检查
python3 completion-relay/completion_listener.py --once

# 持续监听
python3 completion-relay/completion_listener.py --loop --interval 60
```

15 个单元测试: `python3 -m pytest completion-relay/tests/ -v`

### l2_capabilities.py

6 个 L2 增强能力的演示实现：ACK 协议、Handoff 模板、交付物分层、单写入者规则、Follow-up 桥接、每日反思管线。

```bash
python3 l2_capabilities.py
```

35 个单元测试: `python3 -m pytest tests/test_l2_capabilities.py -v`

### protocol_messages.py

协议消息格式（request/ack/final）的构造和解析演示，对应 AGENT_PROTOCOL.md 规范。

```bash
python3 protocol_messages.py
```

## 已废弃

以下示例已在 v2 中移除：

| 示例 | 移除原因 | 替代方案 |
|------|----------|----------|
| mini-watcher/ | 基于文件轮询（行业反模式） | completion-relay/ + spawn-interceptor plugin |
| task_state_machine.py | 基于旧 watcher 状态机 | spawn-interceptor 自动追踪 |
| test-protocol.sh | 过时的测试脚本 | completion-relay/tests/ |

详见 [COMMUNICATION_ISSUES.md](../COMMUNICATION_ISSUES.md) 了解为什么从文件轮询迁移到 plugin hook + 完成回调。

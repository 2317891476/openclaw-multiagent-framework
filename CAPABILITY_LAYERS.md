# 当前能力分层表

> Version: 2026-03-12-v1  
> 目标：明确哪些是 OpenClaw 默认能力、哪些是我们额外补的、哪些还需要改 core

---

## 能力分层总览

| 层级 | 说明 | 数量 | 状态 |
|------|------|------|------|
| **L1: OpenClaw 默认自带** | 无需额外实现，开箱即用 | 8 项 | ✅ 稳定 |
| **L2: 我们额外补的增强** | workspace 层实现，可复制到其他团队 | 12 项 | ✅ 已落地 |
| **L3: 需要改 OpenClaw Core** | 当前仓库无法完全解决，需要 core 支持 | 4 项 | ⏳ 待推进 |

---

## L1: OpenClaw 默认自带（8 项）

| # | 能力 | 说明 | 使用方式 |
|---|------|------|----------|
| 1 | `sessions_send` | Agent 间控制面通信 | 内置工具 |
| 2 | `sessions_spawn` | 后台子任务执行 | 内置工具 |
| 3 | `message` 工具 | 对外频道播报 | 内置工具 |
| 4 | Discord 频道绑定 | 每个 agent 有独立 session lane | 配置层 |
| 5 | cron 定时任务 | 支持 cron 表达式 + 时区 | `cron/jobs.json` |
| 6 | 基础 session 管理 | 自动持久化聊天历史 | 内置 |
| 7 | 工具调用机制 | 支持 bash/exec/browser 等 | 内置 |
| 8 | Gateway 健康检查 | `openclaw gateway status` | CLI |

**特点**：
- 无需额外代码
- 文档齐全
- 社区通用

---

## L2: 我们额外补的增强（12 项）

### 2.1 协作协议层（4 项）

| # | 能力 | 文件位置 | 说明 |
|---|------|----------|------|
| 2.1.1 | ACK 守门协议 | `shared-context/AGENT_PROTOCOL.md` | 先 ACK 再处理，3 秒内必须回执 |
| 2.1.2 | handoff 标准模板 | `AGENT_PROTOCOL.md` 附录 A | request/ack/final 三段式 |
| 2.1.3 | 交付物三层结构 | `AGENTS.md` | 结论 + 证据 + 动作 |
| 2.1.4 | 单写入者规则 | `AGENT_PROTOCOL.md` | 避免多线程竞争写入 |

### 2.2 任务监控层（4 项）

| # | 能力 | 文件位置 | 说明 |
|---|------|----------|------|
| 2.2.1 | task-watcher 终态播报 | `skills/task_callback_bus/` | 任务完成自动推送 |
| 2.2.2 | follow-up/dispatch bridge | `terminal_bridge.py` | 完成后自动生成下一步待办 |
| 2.2.3 | ACP 任务监控注册 SOP | `runbooks/acp-monitor-registration-sop.md` | ACP 任务不允许裸启动 |
| 2.2.4 | generic-exec adapter | `adapters.py` | 支持 exec/sessions_spawn/file_state 三类任务 |

### 2.3 展示层（2 项）

| # | 能力 | 文件位置 | 说明 |
|---|------|----------|------|
| 2.3.1 | Discord 单帖状态面板 | `discord_task_panel.py` | 同一条消息持续 edit 更新 |
| 2.3.2 | watcher→panel 自动桥 | `discord_panel_bridge.py` | 状态变化自动触发面板刷新 |

### 2.4 治理层（2 项）

| # | 能力 | 文件位置 | 说明 |
|---|------|----------|------|
| 2.4.1 | 每日反思→次日落地 | `shared-context/followups/` + cron | 09:05 自动检查 |
| 2.4.2 | Guardian 白天 warn-only | `heartbeat-guardian.sh` | 活跃时段抑制 DEGRADED 重启 |

**特点**：
- 全部可复制到其他 OpenClaw 部署
- 不需要改 core
- 已经有完整文档和模板

---

## L3: 需要改 OpenClaw Core（4 项）

| # | 能力 | 当前缺口 | 建议改动位置 | 优先级 |
|---|------|----------|-------------|--------|
| 3.1 | `sessions_send` 返回值语义拆分 | 只有 ok/timeout，无法区分"已送达"vs"已处理" | Gateway 层消息投递确认 | P0 |
| 3.2 | Fire-and-forget 模式 | 不支持即发即离，必须等 LLM 处理完 | Tool 参数扩展 | P0 |
| 3.3 | 全局 ACK 状态服务 | ACK 状态分散，无法全局查询 | Core 状态服务 | P1 |
| 3.4 | Session Lane 优先级 | 用户消息和 agent 消息同队列，无法插队 | 调度器重写 | P2 |

**详细说明**：

### 3.1 sessions_send 返回值语义拆分

**当前问题**：
```json
// 现在只有两种状态
{"status": "ok"}      // LLM 处理完成
{"status": "timeout"} // 超时（但不知道是投递超时还是处理超时）
```

**期望行为**：
```json
{
  "status": "accepted",
  "delivery": {
    "state": "queued",
    "estimated_wait_ms": 45000,
    "queue_position": 3
  },
  "tracking": {
    "ack_id": "tsk_xxx",
    "status_file": "shared-context/job-status/tsk_xxx.json"
  }
}
```

**改动位置**（推测）：
- Gateway 层的消息投递确认
- Session 管理器的队列状态暴露
- Tool 返回值的 schema 扩展

### 3.2 Fire-and-forget 模式

**当前问题**：
`sessions_send` 同步阻塞直到 LLM 返回，无法做到"投递成功即返回"。

**期望行为**：
```python
sessions_send(
    agent_id="ainews",
    message="...",
    ack_id="tsk_001",
    fire_and_forget=True,  # 投递成功即返回，不等 LLM 处理
    callback_channel="discord:123456"  # 终态通过 watcher 回推
)
# 立即返回：{"status": "delivered", "ack_id": "tsk_001"}
```

### 3.3 全局 ACK 状态服务

**当前问题**：
ACK 状态分散在各 agent 本地，无法全局查询"这个 ack_id 到底什么状态"。

**期望行为**：
```python
get_ack_status(ack_id="tsk_001")
# 返回：{agent, state, acked_at, completed_at, report_file}
```

### 3.4 Session Lane 优先级

**当前问题**：
用户消息和 agent 消息在同一个 lane 排队，无法区分优先级。

**期望行为**：
```
Lane Priority:
- P0: 用户直接消息 (可中断当前 agent 处理)
- P1: Agent 紧急控制面
- P2: Agent 普通协作
- P3: 后台异步任务
```

---

## 对外部用户的建议

### 如果你刚接触这个框架

**建议学习顺序**：
1. 先掌握 **L1 默认能力**（OpenClaw 文档已有）
2. 再引入 **L2 增强能力**（本框架核心贡献）
3. **L3 缺口**暂时用变通方案，等 core 支持

### 如果你要部署到自己团队

**最小可用集合**（建议优先引入）：
1. ACK 守门协议（2.1.1）
2. handoff 标准模板（2.1.2）
3. task-watcher 终态播报（2.2.1）
4. 每日反思→次日落地（2.4.1）

**进阶集合**（稳定后再引入）：
- follow-up/dispatch bridge（2.2.2）
- Discord 面板自动刷新（2.3.1 + 2.3.2）
- Guardian 白天 warn-only（2.4.2）

### 如果你遇到 L3 相关问题

**当前变通方案**：
| 缺口 | 变通方案 |
|------|----------|
| sessions_send timeout | 按"ambiguous success"处理，通过 watcher/状态文件追踪终态 |
| 无法 fire-and-forget | 用 `sessions_spawn(mode="run")` + task-watcher 替代 |
| 无法全局查 ACK | 用 `shared-context/job-status/ack-state-bridge.py` 本地桥接 |
| 无法优先级插队 | 用 `timeoutSeconds` 区分紧急程度，人工介入 |

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 2026-03-12-v1 | 2026-03-12 | 初始版本 |

---

*本文档是开源包的一部分，完整框架见：`https://github.com/lanyasheng/openclaw-multiantent-framework`*

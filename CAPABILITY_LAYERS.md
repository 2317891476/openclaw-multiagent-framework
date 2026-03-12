# 能力分层模型

> Version: 2026-03-12-v2

---

## 分层概览

| 层 | 来源 | 复杂度 | 说明 |
|----|------|--------|------|
| **L1** | OpenClaw 默认 | 零配置 | sessions_send、sessions_spawn、文件系统等内置工具 |
| **L2** | 本框架增强 | 低（plugin + 脚本） | 自动任务追踪、ACK 守门、handoff 模板、完成回调 |
| **L3** | 需 Core 修改 | 高 | 需要 OpenClaw 核心代码变更（如修复 ACP notifyChannel bug） |

---

## L1：OpenClaw 默认能力

### 通信
- `sessions_send`：同步/短异步消息传递
- `sessions_spawn`：启动子 Agent（subagent / ACP）

### 存储
- 文件系统读写（`shared-context/` 等）

### 执行
- 工具调用（MCP tools、built-in tools）
- ACP 远程执行

### 限制
- ACP 完成没有可靠通知（Bug #40272）
- `sessions_spawn` timeout 语义模糊（Issue #28053）
- 无原生任务状态追踪

---

## L2：本框架增强能力

### 2.1 自动任务追踪（spawn-interceptor plugin）

**实现**：`plugins/spawn-interceptor/index.js`

**能力**：
- 自动拦截所有 `sessions_spawn` 调用
- 记录到 `task-log.jsonl`（时间、agent、runtime、任务摘要）
- ACP 任务自动注入完成回调指令

**Agent 负担**：零——正常使用 `sessions_spawn` 即可

### 2.2 完成通知（completion-listener）

**实现**：`examples/completion-relay/completion_listener.py`

**能力**：
- 监听 `agent:main:completion-relay` session
- 解析 ACP 完成通知
- 更新 task-log 状态
- 可扩展到 Discord/Telegram 通知

**Agent 负担**：ACP Agent 只需按注入的回调指令执行 `sessions_send`

### 2.3 ACK 守门协议

**实现**：协议规范（`AGENT_PROTOCOL.md` 第 4 章、第 11 章）

**能力**：
- 收到 Request 后 3 秒内强制 ACK
- ACK 后才执行实际工作
- 状态落盘 `job-status/{ack_id}.json`

**Agent 负担**：遵循协议规范

### 2.4 Handoff 标准模板

**实现**：协议规范（`AGENT_PROTOCOL.md` 附录 A）

**能力**：
- Request/ACK/Final 三段式模板
- 交付物三层结构（结论 + 证据 + 动作）
- 可直接复用的消息模板

### 2.5 真值落盘

**实现**：协议规范 + 目录结构

**能力**：
- 关键事实必须写入 `shared-context/`
- 验收优先检查文件产物
- 状态枚举：spawning → in_progress → completed/failed

### 2.6 反思落地闭环

**实现**：协议规范（`AGENT_PROTOCOL.md` 第 7 章）

**能力**：
- 每日反思产出 `followups/YYYY-MM-DD.md`
- 次日 09:30 前转成实际动作
- P0/P1 强制跟进

---

## L3：需要 Core 修改

### 3.1 ACP notifyChannel

**Issue**：#40272

**现状**：ACP 完成后不触发 `notifyChannel`，导致无原生完成通知

**当前绕过**：spawn-interceptor 注入 prompt 让 ACP Agent 主动 `sessions_send`

**理想修复**：OpenClaw core 修复 `notifyChannel`，ACP 完成自动通知

### 3.2 sessions_spawn 明确返回值

**Issue**：#28053

**现状**：`sessions_spawn` 超时时无法区分"未投递"和"投递成功但执行超时"

**当前绕过**：task-log 记录 spawning 状态，后续通过 completion 确认

**理想修复**：`sessions_spawn` 返回明确的投递确认

### 3.3 before_tool_call hook 完整支持

**Issue**：#5943

**现状**：`before_tool_call` hook 可能未在所有场景中触发

**当前绕过**：测试确认当前版本 hook 已可用

**理想修复**：OpenClaw 官方文档明确 hook 生命周期

---

## 能力矩阵

| 能力 | L1 | L2 (本框架) | L3 |
|------|----|-----------|----|
| Agent 间消息传递 | ✅ sessions_send | ✅ + ACK 守门 | — |
| 启动子 Agent | ✅ sessions_spawn | ✅ + 自动追踪 | — |
| ACP 完成通知 | ❌ Bug #40272 | ✅ prompt 注入回调 | 🔧 修复 notifyChannel |
| 任务状态追踪 | ❌ | ✅ task-log.jsonl | — |
| 标准协作模板 | ❌ | ✅ handoff 模板 | — |
| 真值落盘 | ❌ | ✅ shared-context/ | — |
| 反思闭环 | ❌ | ✅ followups/ | — |

---

## 引入路径

```
第 1 周: L2.1 + L2.2（安装 plugin + listener → 自动任务追踪）
第 2 周: L2.3 + L2.4（ACK 守门 + handoff 模板 → 协作规范）
第 3 周: L2.5 + L2.6（真值落盘 + 反思闭环 → 完整体系）
持续关注: L3 issues，等待 OpenClaw core 修复
```

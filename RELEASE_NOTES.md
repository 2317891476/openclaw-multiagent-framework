# Release Notes

---

## v2.2.0 — Completion 回传修复 + 防御增强 (2026-03-13)

### 核心修复
- **completion 回传闭环修复**: 用 subagent_ended hook 作为 PRIMARY 完成检测机制
  - 之前依赖 prompt 注入 sessions_send 指令，但 ACP agent 完成主任务后直接退出
  - 现在 subagent_ended 是系统事件，由 Gateway 自动触发，不依赖 agent 行为
- **Stale Task Reaper**: 每 5 分钟扫描，超过 30 分钟未完成的自动标记 timeout
- **持久化 pending state**: .pending-tasks.json 确保 Gateway 重启不丢失追踪状态
- **completion_listener v2**: 直接从 task-log.jsonl 读取完成状态

### 防御机制
| 场景 | 防御 |
|------|------|
| 正常完成 | subagent_ended hook → completed |
| Gateway 断开 | 持久化恢复 + stale reaper → timeout |
| ACP 崩溃 | subagent_ended(reason=error) → failed |

### 已知 OpenClaw Bug
新增 Bug 追踪章节：#34054, #35886, #40243, #40272

---

## v2.0.0 — 通信层重设计 (2026-03-12)

### 核心变更：从文件轮询到拦截 + 回调

**问题背景**：
1. ACP 任务完成后没有可靠通知机制（ACP `notifyChannel` bug - Issue #40272）
2. `sessions_spawn` timeout 语义歧义（Issue #28053）
3. Agent 忘记执行监控步骤（LLM 固有局限）

为解决这三个问题，之前自建了 ~9,600 行的 `task_callback_bus`（文件轮询架构），现替换为 ~600 行的 plugin + listener 方案。

### 新增

- **spawn-interceptor plugin**（`plugins/spawn-interceptor/`）
  - 自动拦截 `sessions_spawn` 调用
  - 记录到 `task-log.jsonl`
  - 为 ACP 任务注入完成回调指令
  - 符合 OpenClaw plugin 规范（`register(api)` + `openclaw.plugin.json`）

- **completion-listener**（`examples/completion-relay/`）
  - 监听 `agent:main:completion-relay` session
  - 解析完成通知并更新 task-log
  - 可扩展到 Discord/Telegram

- **COMMUNICATION_ISSUES.md**
  - 核心设计文档，完整记录问题、方案、架构和实现

- **QUICKSTART.md v3**
  - 全面重写，5 分钟部署 plugin + listener
  - 涵盖验证、故障排查、清单

### 变更

- **ARCHITECTURE.md**：新增"通信层改进"章节
- **ANTIPATTERNS.md**：新增 #11 文件轮询反模式、#12 文档约束反模式
- **README.md**：重写为 plugin + 协议框架定位
- **GETTING_STARTED.md**：更新决策树和 MVP 集合
- **INTERNAL_VS_OSS.md**：反映开源包已包含可运行代码
- **CONTRIBUTING.md**：更新贡献范围和代码规范

### 移除

- `examples/mini-watcher/`（文件轮询反模式）
- `examples/task_state_machine.py`（已由 plugin 替代）
- `examples/test-protocol.sh`（已过时）
- `PROJECT_STATUS.md`（内部文档不应开源）

### 代码量对比

| 方案 | 行数 | 文件数 |
|------|------|--------|
| task_callback_bus（旧） | ~9,600 | ~40+ |
| spawn-interceptor + completion-relay（新） | ~600 | 6 |

### 测试

- completion-relay: 15 个测试
- l2_capabilities: 35 个测试
- 全部通过

---

## v1.0.0 — 协议框架初版 (2026-03-12)

### 新增

- **AGENT_PROTOCOL.md**: 五角色 Agent 协作协议
- **ARCHITECTURE.md**: 三层架构（L1/L2/L3）
- **QUICKSTART.md**: 快速开始指南
- **CAPABILITY_LAYERS.md**: 能力分层模型
- **ANTIPATTERNS.md**: 常见反模式（10 条）
- **TEMPLATES.md**: 标准消息模板
- **GETTING_STARTED.md**: 开源接入指引
- **examples/**: protocol_messages.py, l2_capabilities.py
- **tests/**: 35 个测试用例

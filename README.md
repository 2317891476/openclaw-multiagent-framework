# OpenClaw 多 Agent 协作框架

> 统一、高效、可追溯的多 Agent 团队协作协议与架构模式

**Version**: 2026-03-12-v2
**License**: MIT
**Status**: Production Ready (内部验证) / OSS Ready
**作者**: lanyasheng (OpenClaw 社区)

---

## 一句话说明

这是一套**经过实战验证的 OpenClaw 多 Agent 协作框架**，解决 ACP 异步通信不可靠、Agent 遗忘任务注册、timeout 语义模糊三大痛点。

---

## 解决什么问题

| 问题 | 根因 | 本框架方案 |
|------|------|------------|
| ACP 任务完成没通知 | OpenClaw Bug #40272 (notifyChannel 不转发) | spawn-interceptor plugin 自动注入完成回调 |
| Agent 忘记注册监控 | LLM 肌肉记忆指向原生工具 | before_tool_call hook 自动拦截 |
| timeout 不知道成败 | sessions_send 只有 ok/timeout | task-log 确定性追踪 |
| 长任务执行 | 同步等待 or 口头催办 | 后台执行 + 完成回调推送 |
| 跨 Agent 协作 | 自由格式，难以追溯 | 标准 handoff 模板 (request/ack/final) |
| 真值管理 | 依赖聊天历史 | 状态文件 + 报告文件双落盘 |

详见 [COMMUNICATION_ISSUES.md](COMMUNICATION_ISSUES.md) — 完整的问题分析和设计方案。

---

## 核心架构

```
Agent -> sessions_spawn(acp)
    | (before_tool_call hook 自动拦截)
spawn-interceptor plugin:
    1. 记录到 task-log.jsonl
    2. 注入完成回调指令到 ACP prompt
    |
ACP 子 Agent 执行任务
    | (完成时)
ACP -> sessions_send -> completion-relay session
    |
completion-listener -> 更新 task-log -> 通知用户
```

**零认知负担**: Agent 不需要记住额外步骤，系统自动处理。

---

## 快速开始

### 前置条件

- OpenClaw >= 2026.3.x（需支持 before_tool_call plugin hook）
- Python 3.10+
- 至少 1 个 Agent 配置

### 部署 spawn-interceptor plugin

```bash
# 1. 复制 plugin
cp -r plugins/spawn-interceptor ~/.openclaw/plugins/

# 2. 注册到 openclaw.json
# 在 plugins.allow 数组中添加 "spawn-interceptor"
# 在 plugins.entries 中添加 {"spawn-interceptor": {"enabled": true}}

# 3. 重启 Gateway
kill $(pgrep -f openclaw-gateway)
openclaw gateway start
```

### 部署 completion-listener

```bash
# 添加到 crontab (每分钟检查一次)
echo "*/1 * * * * cd ~/.openclaw/repos/openclaw-multiagent-framework/examples/completion-relay && python3 completion_listener.py --once >> /tmp/completion-relay.log 2>&1" | crontab -

# 或手动运行
python3 examples/completion-relay/completion_listener.py --loop
```

### 验证

```bash
# 触发一个 ACP 任务后，检查 task-log
tail -f ~/.openclaw/shared-context/monitor-tasks/task-log.jsonl
```

详细部署指南见 [QUICKSTART.md](QUICKSTART.md) 和 [GETTING_STARTED.md](GETTING_STARTED.md)。

---

## 文档导航

| 文档 | 用途 | 阅读顺序 |
|------|------|----------|
| `README.md` | 框架说明（本文档） | 1 |
| `COMMUNICATION_ISSUES.md` | 通信层问题分析与设计方案 | 2 |
| `GETTING_STARTED.md` | 接入指引 | 3 |
| `QUICKSTART.md` | 快速部署指南 | 4 |
| `AGENT_PROTOCOL.md` | 完整协议规范 | 5 |
| `ARCHITECTURE.md` | 架构设计（含新通信层） | 6 |
| `CAPABILITY_LAYERS.md` | 能力分层表 (L1/L2/L3) | 7 |
| `ANTIPATTERNS.md` | 踩坑实录 | 8 |
| `TESTING.md` | 测试架构与运行指南 | 9 |
| `TEMPLATES.md` | 消息和文件模板 | 10 |
| `INTERNAL_VS_OSS.md` | 开源包 vs 内部运行版差异 | 11 |
| `CONTRIBUTING.md` | 贡献方式与提交流程 | 12 |

---

## 仓库结构

```
.
├── COMMUNICATION_ISSUES.md    # 通信层问题分析与设计方案（核心文档）
├── AGENT_PROTOCOL.md          # 协作协议规范
├── ARCHITECTURE.md            # 架构设计
├── CAPABILITY_LAYERS.md       # 能力分层 (L1/L2/L3)
├── ANTIPATTERNS.md            # 踩坑实录
├── plugins/
│   └── spawn-interceptor/     # OpenClaw plugin — 自动任务追踪
│       ├── index.js           # Plugin 实现 (before_tool_call + subagent_ended)
│       ├── package.json
│       └── README.md
├── examples/
│   ├── completion-relay/      # 完成通知监听器
│   │   ├── completion_listener.py
│   │   ├── tests/
│   │   └── README.md
│   ├── l2_capabilities.py     # L2 能力演示代码
│   └── protocol_messages.py   # 协议消息格式演示
└── ...
```

---

## 设计哲学

> **如果一个行为是强制的，它就不应该是可选的。**

旧方案要求 Agent "记住"用 wrapper 注册 watcher（文档约束）。
新方案用 plugin hook 自动拦截（系统约束）。

详见 [COMMUNICATION_ISSUES.md](COMMUNICATION_ISSUES.md) 第 6 节。

---

## 许可证

MIT License

## 贡献

欢迎 PR 和 Issue。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

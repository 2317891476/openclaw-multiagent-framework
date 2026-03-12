# 开源包 vs 内部运行版差异说明

> Version: 2026-03-12-v2
> 目标：明确告知外部用户开源包与内部实际运行版本的区别

---

## 核心结论

**开源包提供完整的通信层 plugin + 协作协议框架。内部版在此基础上有更多业务实现。**

| 维度 | 开源包 | 内部运行版 |
|------|--------|------------|
| **定位** | 通信层 plugin + 协议框架 | 完整生产系统 |
| **可直接运行** | ✅ plugin + listener 可直接部署 | ✅ 完整运行 |
| **包含实现代码** | ✅ spawn-interceptor + completion-relay | ✅ 全量代码 |
| **Agent 角色** | 通用模板 | trading/macro/ainews/content/butler |
| **业务逻辑** | 脱敏示例 | 完整金融/交易规则 |
| **配置信息** | 占位符 | 真实配置 |

---

## 详细差异对照

### 1. 开源包包含的可运行组件

| 组件 | 类型 | 说明 |
|------|------|------|
| `plugins/spawn-interceptor/` | Node.js plugin | 自动追踪 sessions_spawn + 注入 ACP 完成回调 |
| `examples/completion-relay/` | Python 脚本 | 监听完成通知 + 更新 task-log |
| `examples/l2_capabilities.py` | Python 演示 | 6 项 L2 能力的参考实现 |
| `examples/protocol_messages.py` | Python 演示 | 协议消息格式验证 |

### 2. 内部版额外组件（未开源）

| 组件 | 说明 | 开源替代 |
|------|------|----------|
| `task-callback-bus/` (2,543 行) | 事件驱动任务监控 (WatcherBus + DLQ + Terminal Bridge + Agent Guardrail) | spawn-interceptor plugin (150 行) |
| `discord_task_panel.py` | Discord 面板实现 | 自行实现 |
| `terminal_bridge.py` | follow-up 桥接 | 自行实现 |
| `heartbeat-guardian.sh` | Guardian 自愈脚本 | 自行实现 |

### 3. 配置与密钥

| 类型 | 开源包 | 内部版 |
|------|--------|--------|
| Channel ID | `<channel-id>` | 真实 Discord ID |
| API 密钥 | 不包含 | 真实密钥（本地存储） |
| Gateway 配置 | 示例说明 | 真实 `openclaw.json` |

---

## 外部用户如何使用

### 推荐路径

```
1. 阅读 README.md → 理解框架定位
2. 安装 spawn-interceptor plugin → 自动任务追踪
3. 部署 completion-listener → 接收完成通知
4. 学习 AGENT_PROTOCOL.md → 理解协议规范
5. 运行测试 → 确认组件正常（50 个测试）
```

---

## 常见问题

### Q1: 开源包能直接运行吗？

**A**: plugin 和 listener 可以直接部署。协议文档需要根据你的团队适配。

### Q2: 还需要自建 task-watcher 吗？

**A**: 不需要。`spawn-interceptor` plugin + `completion-listener` 替代了旧的文件轮询 watcher，用事件驱动的方式追踪任务。

### Q3: 开源包会更新吗？

**A**: 会。更新节奏：
- 通信层 plugin：随 OpenClaw API 变化更新
- 协议文档：随最佳实践积累更新
- 测试：持续完善

---

## 版本对齐

| 版本 | 日期 | 内容 |
|------|------|------|
| v1 | 2026-03-12 | 首次发布：协议文档 + 文档框架 |
| v2 | 2026-03-12 | 通信层重设计：spawn-interceptor plugin + completion-relay |

---

## 反馈与建议

如果你在使用过程中发现问题，请在 GitHub Issues 中反馈。

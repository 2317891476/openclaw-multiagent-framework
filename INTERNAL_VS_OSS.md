# 开源包 vs 内部运行版差异说明

> Version: 2026-03-12-v1  
> 目标：明确告知外部用户开源包与内部实际运行版本的区别

---

## 核心结论

**开源包是"可迁移的协作规范框架"，不是"内部运行的完整镜像导出"。**

| 维度 | 开源包 | 内部运行版 |
|------|--------|------------|
| **定位** | 文档框架 + 协议模板 | 完整生产系统 |
| **可直接运行** | ⚠️ 需适配 | ✅ 是 |
| **包含实现代码** | ❌ 否（仅文档） | ✅ 是 |
| **Agent 角色** | 通用模板 | trading/macro/ainews/content/butler |
| **业务逻辑** | 脱敏示例 | 完整金融/交易规则 |
| **配置信息** | 占位符 | 真实配置 |

---

## 详细差异对照

### 1. 文档完整性

| 文档 | 开源包 | 内部版 | 差异说明 |
|------|--------|--------|----------|
| `AGENT_PROTOCOL.md` | ✅ 完整 | ✅ 完整 | 开源版约 3300 字符，内部版约 8000 字符（含更多细节） |
| `ARCHITECTURE.md` | ✅ 完整 | ✅ 完整 | 基本一致 |
| `QUICKSTART.md` | ✅ 完整 | ✅ 完整 | 基本一致 |
| `TEMPLATES.md` | ✅ 完整 | ✅ 完整 | 基本一致 |
| `CAPABILITY_LAYERS.md` | ✅ 完整 | ✅ 完整 | 基本一致 |
| `acp-monitor-registration-sop.md` | ❌ 不包含 | ✅ 包含 | 内部 SOP，暂未开源 |

### 2. 实现代码

| 组件 | 开源包 | 内部版 | 说明 |
|------|--------|--------|------|
| `task_callback_bus/` | ❌ 不包含 | ✅ 完整 | 任务监控核心实现 |
| `discord_task_panel.py` | ❌ 不包含 | ✅ 完整 | Discord 面板实现 |
| `terminal_bridge.py` | ❌ 不包含 | ✅ 完整 | follow-up/dispatch 桥接 |
| `discord_panel_bridge.py` | ❌ 不包含 | ✅ 完整 | watcher→panel 自动桥 |
| `heartbeat-guardian.sh` | ❌ 不包含 | ✅ 完整 | Guardian 自愈脚本 |
| 各类 adapter | ❌ 不包含 | ✅ 完整 | generic-exec 等 |

### 3. Agent 团队配置

| 项目 | 开源包 | 内部版 |
|------|--------|--------|
| Agent 数量 | 通用模板 | 6 个核心 Agent + 后台 |
| 角色定义 | 占位符 | trading/macro/ainews/content/butler/main |
| 职责边界 | 示例 | 详细的 core/non-core/trigger/handoff |
| Session Key | 模板格式 | 真实 session key |

### 4. 业务逻辑

| 领域 | 开源包 | 内部版 |
|------|--------|--------|
| 金融数据 | 脱敏示例 | 完整 AKShare/财经数据接口 |
| 交易规则 | 不包含 | 完整交易分析/晨报/收评流程 |
| 新闻聚合 | 不包含 | 13 源并发抓取 + 5 分钟缓存 |
| 市场锚点 | 概念说明 | 真实 preflight 快照机制 |

### 5. 配置与密钥

| 类型 | 开源包 | 内部版 |
|------|--------|--------|
| Channel ID | `<channel-id>` | 真实 Discord ID |
| Cron 配置 | 示例 | 真实 `cron/jobs.json` |
| API 密钥 | 不包含 | 真实密钥（本地存储） |
| Gateway 配置 | 不包含 | 真实 `openclaw.json` |

---

## 外部用户如何使用

### 推荐路径

```
1. 阅读 README.md → 理解框架定位
2. 运行 QUICKSTART.md → 验证基础能力
3. 学习 AGENT_PROTOCOL.md → 理解协议规范
4. 参考 CAPABILITY_LAYERS.md → 了解 L1/L2/L3 分层
5. 根据自身需求适配 → 引入 L2 增强能力
```

### 最小可用集合（建议优先引入）

1. **ACK 守门协议**（`AGENT_PROTOCOL.md` 第 4 章）
2. **handoff 标准模板**（`AGENT_PROTOCOL.md` 附录 A）
3. **task-watcher 终态播报**（需自行实现或参考内部代码）
4. **每日反思→次日落地**（`AGENT_PROTOCOL.md` 第 7 章）

### 进阶集合（稳定后再引入）

- follow-up/dispatch bridge
- Discord 面板自动刷新
- Guardian 白天 warn-only
- ACP 任务监控注册 SOP

---

## L3 缺口的当前变通方案

| 缺口 | 开源包现状 | 变通方案 |
|------|------------|----------|
| `sessions_send` timeout | 无法区分送达/处理 | 按"ambiguous success"处理，通过 watcher/状态文件追踪 |
| 无法 fire-and-forget | 不支持即发即离 | 用 `sessions_spawn(mode="run")` + task-watcher 替代 |
| 无法全局查 ACK | ACK 状态分散 | 自建 `ack-state-bridge.py` 本地桥接 |
| 无法优先级插队 | 同队列排队 | 用 `timeoutSeconds` 区分紧急程度，人工介入 |

详见 `CAPABILITY_LAYERS.md` 第 3 章。

---

## 常见问题

### Q1: 开源包能直接运行吗？

**A**: 不能直接 1:1 运行。开源包是**文档框架**，提供：
- ✅ 协议规范
- ✅ 模板
- ✅ 架构说明
- ✅ 部署指南

但**不包含**：
- ❌ 实现代码
- ❌ 业务逻辑
- ❌ 配置文件

你需要根据自身需求进行适配。

### Q2: 我想用内部的 task-watcher，能直接复制吗？

**A**: 可以，但需要注意：
1. 内部代码依赖 OpenClaw workspace 结构
2. 需要自行配置 `tasks.jsonl` 和状态文件目录
3. 建议先理解协议规范，再决定是否需要完整实现

### Q3: 我能只引入协议文档，不引入代码吗？

**A**: 可以，这是推荐做法。先引入：
1. `AGENT_PROTOCOL.md` → 统一协作规范
2. `TEMPLATES.md` → 标准化消息格式
3. `followups/` → 每日反思落地

代码实现可以后续根据需要自行开发。

### Q4: 开源包会更新吗？

**A**: 会。更新节奏：
- 协议文档：随内部验证后脱敏更新
- 模板：随最佳实践积累更新
- 实现代码：暂不开源，仅提供参考架构

---

## 版本对齐

| 版本 | 日期 | 开源包 | 内部版 |
|------|------|--------|--------|
| v1 | 2026-03-12 | ✅ 发布 | ✅ 运行中 |

**注意**：开源包版本可能略微落后于内部最新实现，但核心协议保持一致。

---

## 反馈与建议

如果你在使用过程中发现：
- 文档与实际不符
- 缺少关键说明
- 需要更多示例

请在 GitHub Issues 中反馈，我们会优先补充。

# AGENT_PROTOCOL.md — 团队统一协作协议（脱敏开源版）

<!-- 阅读顺序: 3/5 -->
<!-- 前置: QUICKSTART.md -->
<!-- 后续: ARCHITECTURE.md -->

> Version: 2026-03-12-v1
> Owner: main (Zoe)
> Scope: All agents
> Status: Canonical

---

## 1. 目标

统一以下原本分散的规则：
- ACK 守门
- Agent 间控制面通信
- 长任务异步执行与回推
- 共享状态落盘
- 每日反思的次日 P0/P1 跟进闭环

**从现在开始，以本文件为唯一规范入口。**

---

## 2. 三层分工

### 2.1 控制面：`sessions_send`
用于：派单、ACK、催办、简短结论、正式控制面消息。

### 2.2 异步回执面：`task-watcher`
用于：>10 秒长任务、后台任务、状态变化任务的终态通知。

### 2.3 共享状态面：`shared-context/*`
用于：协议、任务真值、中间状态、follow-up、intel、dispatches。

**规则**：关键事实不能只留在聊天历史里，必须落共享状态。

---

## 3. 双阈值规则（强制）

- `<= 3 秒`：允许同步完成
- `> 3 秒`：必须先 ACK
- `> 10 秒`：必须异步执行，并接入 task-watcher 或等价状态回推机制

标准链路：
`ACK -> 后台执行 -> 写 status/report -> terminal push`

---

## 4. ACK 守门（P0 强制）

适用范围：
- 用户追问
- `sessions_send`
- 跨 Agent intel 同步
- 带 `request_id / ack_id` 的正式控制面消息

硬规则：
1. **先 ACK，再处理**
2. 禁止先查文件、等线程、做分析而不回复
3. 若当前主线繁忙，也必须先做最小 ACK
4. 任何 >3 秒动作不得在 ACK 前或 ACK 后当前回合同步等待结果
5. 多线并行时，必须区分主线 / 支线 / 内控线，避免串线

ACK 最小格式：
- 对用户：`收到，正在查 X / 正在推进 Y`
- 对 agent：`[ACK] ack_id=<id> state=confirmed | 正在处理 <topic>`

---

## 5. 长任务执行规范（P0 强制）

符合以下任一条件，默认异步：
- 多次工具调用
- 文件系统搜索 / 日志扫描 / 网络抓取
- 长文生成
- 等待外部状态变化
- 子任务委派

执行顺序固定：
1. 当前会话先 ACK
2. 生成 `task_id`
3. 先注册 watcher / 状态文件
4. 再启动后台执行（`sessions_spawn(mode="run")` 或 `exec(background=true)`）
5. 终态由 watcher 或单一 terminal owner 回推

禁止：
- 把 `sessions_send` 当同步 RPC 长等完整结果
- 当前回合同步等待 ACP / agent / thread 回执
- 一个异步任务发出两条 final

---

## 6. 共享状态与真值规则

关键状态必须落到以下位置：
- `shared-context/job-status/`
- `shared-context/monitor-tasks/`
- `shared-context/dispatches/`
- `shared-context/intel/`
- `shared-context/followups/`

验收真值顺序：
1. 核心产物是否存在
2. `status_file` 是否一致
3. `report_file` 是否存在
4. 测试/日志是否通过
5. 最后才看聊天回执

**completed 不能只看状态字样，必须核真实产物。**

---

## 7. 每日反思 → 次日 P0/P1 落地链路（P0 强制）

### 7.1 原则
**反思完成 ≠ 落地完成。**

每日反思中写出的"明日重点 / P0 / P1"，第二天必须转成明确动作，不能只停留在总结文本里。

### 7.2 固定落地物
每个自然日必须有一份：
- `shared-context/followups/YYYY-MM-DD.md`

其中至少包含：
- 事项
- Priority（P0/P1）
- Owner
- 来源（出自哪份反思）
- 当前状态（pending/in_progress/done/blocked）
- 证据路径（dispatch / intel / report / runbook / code / message）

### 7.3 固定时间点
- **前一日晚间反思结束后**：写出次日 follow-up 初稿
- **次日 09:00 前**：main 完成 review，确认当天 P0/P1
- **次日 09:30 前**：相关事项必须转成实际动作（dispatch / task / file / sync）
- **次日 20:30 前**：更新状态；未完成项要么说明 blocker，要么 rollover 到下一天

### 7.4 验收标准
以下任一缺失，都不算"已落实"：
- 没有 owner
- 没有证据路径
- 没有实际派单/文件/任务注册
- 只有反思文本，没有第二天动作

### 7.5 main 的职责
main 每天必须回答两个问题：
1. 昨天反思里的 P0/P1，今天哪些已经转成实际动作？
2. 哪些还没转？为什么？谁负责？

---

## 8. 正式控制面消息格式（推荐）

```text
[Request] ack_id=<id> | topic=<topic> | ask=<what> | due=<time>
[ACK] ack_id=<id> state=confirmed | handling=<summary>
[Final] ack_id=<id> state=final | result=<summary>
```

闭环后"收到/感谢/OK"统一 `NO_REPLY`。

---

## 9. 单写入者（single-writer）规则

适用：重开任务、rerun、fallback、并发子任务。

规则：
1. 旧线程一旦被替代，必须停写
2. 新线程成为唯一合法 owner
3. owner 必须落文件
4. 最终补旧线程 superseded / terminal close

---

## 10. 现阶段唯一规范入口

- 协议总入口：`~/.openclaw/shared-context/AGENT_PROTOCOL.md`
- 历史设计/审计/实现文档：归档到 `~/.openclaw/shared-context/archive/protocol-history/`

如果旧文档与本文件冲突，以本文件为准。

---

## 11. 今日执行要求（立即生效）

1. 所有 agent 读取并遵守本文件
2. 后续引用协议时，只引用本文件路径
3. 每日反思必须产出次日 `followups/YYYY-MM-DD.md`
4. 每日 09:30 前，P0/P1 必须至少转成一条可验证动作

---

## 脱敏说明

本文件为开源脱敏版本，已移除：
- 具体 Discord channel ID
- 具体 sessionKey
- 具体 agent ID
- 其他团队特定标识符

在实际使用时，请根据自己团队的配置替换相关标识符。
